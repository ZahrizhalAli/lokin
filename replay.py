"""Replay a recorded Lokin session offline.

Re-feeds a session recorded by ``SessionRecorderObserver`` (user turns and
screen-share frames, with their original timing driven by a virtual clock)
through the same screen-injector -> LLM stages used by app.py — no browser,
no microphone, no TTS. Bot responses are regenerated live by the LLM, so
you can change pipeline code or prompts and see how the same session plays
out; the recorded responses are printed alongside for comparison.

Requires OPENAI_API_KEY. Usage::

    uv run replay.py sessions/<session-id>
"""

import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from loguru import logger

from lokin.frames.frames import (
    InputImageRawFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from lokin.pipeline.pipeline import Pipeline
from lokin.pipeline.runner import PipelineRunner
from lokin.pipeline.task import PipelineParams, PipelineTask
from lokin.processors.aggregators.llm_context import LLMContext
from lokin.processors.frame_processor import FrameDirection, FrameProcessor
from lokin.processors.screen_share_injector import ScreenShareContextInjector
from lokin.services.openai.llm import OpenAILLMService

_EXTENSION_MIMES = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class ReplayClock:
    """Virtual clock fed to the injector so recorded timing is reproduced."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class ResponseCollector(FrameProcessor):
    """Terminal processor: aggregates LLM responses and tracks seen frames.

    Tracking seen frame ids lets the replay driver wait until a queued frame
    has traversed the whole pipeline before advancing the virtual clock.
    """

    def __init__(self):
        super().__init__(name="ResponseCollector")
        self._parts = []
        self._response = None
        self._response_ready = asyncio.Event()
        self._seen_ids = set()
        self._seen_changed = asyncio.Event()

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMFullResponseStartFrame):
            self._parts = []
        elif isinstance(frame, LLMTextFrame):
            self._parts.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            self._response = "".join(self._parts)
            self._response_ready.set()
        self._seen_ids.add(frame.id)
        self._seen_changed.set()
        await self.push_frame(frame, direction)

    async def wait_until_seen(self, frame_id: int, timeout: float = 2.0):
        while frame_id not in self._seen_ids:
            self._seen_changed.clear()
            try:
                await asyncio.wait_for(self._seen_changed.wait(), timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Frame {frame_id} never reached the end of the pipeline")
                return

    async def wait_for_response(self, timeout: float = 120.0) -> str:
        await asyncio.wait_for(self._response_ready.wait(), timeout)
        self._response_ready.clear()
        response, self._response = self._response, None
        return response


def _replayable(message) -> bool:
    """Whether a recorded new-context message should be re-added on replay.

    Assistant messages are regenerated live and injected screenshots are
    re-injected by the pipeline itself, so neither is copied from the
    recording.
    """
    if not isinstance(message, dict) or "role" not in message:
        return False
    if message["role"] == "assistant":
        return False
    content = message.get("content")
    if isinstance(content, list):
        return not any(
            isinstance(item, dict) and item.get("type") == "image_ref" for item in content
        )
    return True


def _load_screen_frame(session_dir: str, event: dict) -> InputImageRawFrame:
    path = os.path.join(session_dir, event["file"])
    with open(path, "rb") as f:
        data = f.read()
    extension = path.rsplit(".", 1)[-1]
    frame = InputImageRawFrame(
        image=data,
        size=tuple(event["size"]),
        format=_EXTENSION_MIMES.get(extension, "image/jpeg"),
    )
    frame.transport_source = "screenVideo"
    frame.pts = event.get("pts")
    return frame


async def replay(session_dir: str):
    events_path = os.path.join(session_dir, "events.jsonl")
    with open(events_path, "r", encoding="utf-8") as f:
        events = [json.loads(line) for line in f]

    clock = ReplayClock()
    injector = ScreenShareContextInjector(time_fn=clock)
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    collector = ResponseCollector()
    context = LLMContext()

    pipeline = Pipeline([injector, llm, collector])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(),
        enable_turn_tracking=False,
        idle_timeout_secs=None,
    )
    runner = PipelineRunner(handle_sigint=False)

    async def feed():
        for event in events:
            clock.now = event.get("t", clock.now)

            if event["type"] == "screen_frame":
                frame = _load_screen_frame(session_dir, event)
                await task.queue_frame(frame)
                await collector.wait_until_seen(frame.id)

            elif event["type"] == "llm_run":
                new_messages = [m for m in event["new_messages"] if _replayable(m)]
                if not new_messages:
                    continue
                context.add_messages(new_messages)
                for message in new_messages:
                    print(f"\n[{clock.now:8.2f}s] {message['role']}: {message['content']}")

                await task.queue_frame(LLMContextFrame(context=context))
                response = await collector.wait_for_response()
                context.add_message({"role": "assistant", "content": response})
                print(f"[{clock.now:8.2f}s] bot (replayed): {response}")

            elif event["type"] == "bot_response":
                suffix = " [interrupted]" if event.get("interrupted") else ""
                print(f"[{clock.now:8.2f}s] bot (recorded){suffix}: {event['text']}")

        await task.stop_when_done()

    await asyncio.gather(runner.run(task), feed())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", help="Recorded session directory, e.g. sessions/20260704-101500")
    args = parser.parse_args()

    load_dotenv(override=True)
    if not os.path.isfile(os.path.join(args.session_dir, "events.jsonl")):
        sys.exit(f"No events.jsonl found in {args.session_dir}")

    asyncio.run(replay(args.session_dir))


if __name__ == "__main__":
    main()
