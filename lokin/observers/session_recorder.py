"""Session recording for offline debugging and replay.

``SessionRecorderObserver`` watches frames flowing through the pipeline and
writes a per-session event stream to ``<base_dir>/<timestamp>/events.jsonl``:

- user transcriptions and speaking/interruption events
- bot responses (aggregated LLM text)
- LLM context snapshots at each inference, with images saved as files
  under ``images/`` and replaced by ``image_ref`` entries
- screen-share frames, saved as JPEGs so a session can be replayed

Attach it to a task with ``PipelineTask(..., observers=[SessionRecorderObserver()])``.
Recorded sessions can be re-fed through a pipeline offline; see ``replay.py``
at the repository root.
"""

import asyncio
import base64
import hashlib
import io
import json
import os
from collections import deque
from datetime import datetime
from typing import Any, List, Optional

from PIL import Image

from lokin.frames.frames import (
    AudioRawFrame,
    BotSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InputImageRawFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    TranscriptionFrame,
    UserSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from lokin.observers.base_observer import BaseObserver, FramePushed
from lokin.processors.aggregators.llm_context import LLMContext, LLMSpecificMessage
from lokin.services.llm_service import LLMService

_MIME_EXTENSIONS = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}


class SessionRecorderObserver(BaseObserver):
    """Record session events to disk for inspection and replay."""

    def __init__(self, *, base_dir: str = "sessions"):
        super().__init__()
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._dir = os.path.join(base_dir, session_id)
        self._images_dir = os.path.join(self._dir, "images")
        os.makedirs(self._images_dir, exist_ok=True)
        self._file = open(os.path.join(self._dir, "events.jsonl"), "w", encoding="utf-8")
        self._start_ts: Optional[int] = None
        self._seen_frame_ids: set[int] = set()
        self._seen_frame_order: deque[int] = deque()
        self._prev_context_messages: List[Any] = []
        self._bot_text: List[str] = []
        self._emit(0.0, "session_start", wall_time=datetime.now().astimezone().isoformat())

    @property
    def session_dir(self) -> str:
        return self._dir

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame

        # High-frequency heartbeat/audio frames are never recorded.
        if isinstance(frame, (AudioRawFrame, BotSpeakingFrame, UserSpeakingFrame)):
            return

        if self._start_ts is None:
            self._start_ts = data.timestamp
        t = round((data.timestamp - self._start_ts) / 1_000_000_000, 3)

        if isinstance(frame, LLMContextFrame):
            # Snapshot the context exactly as the LLM service receives it,
            # i.e. after upstream processors (e.g. the screen share injector)
            # have modified it.
            if isinstance(data.destination, LLMService):
                await self._record_llm_run(t, frame.context)
            return

        # A frame is pushed once per processor hop; only record it once.
        if not self._first_sighting(frame):
            return

        if isinstance(frame, TranscriptionFrame):
            self._emit(t, "transcription", text=frame.text, user_id=frame.user_id)
        elif isinstance(frame, InterimTranscriptionFrame):
            pass
        elif isinstance(frame, InputImageRawFrame) and frame.transport_source == "screenVideo":
            await self._record_screen_frame(t, frame)
        elif isinstance(frame, LLMTextFrame):
            self._bot_text.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            self._flush_bot_response(t)
        elif isinstance(frame, InterruptionFrame):
            self._flush_bot_response(t, interrupted=True)
            self._emit(t, "interruption")
        elif isinstance(frame, UserStartedSpeakingFrame):
            self._emit(t, "user_started_speaking")
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._emit(t, "user_stopped_speaking")
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._emit(t, "bot_started_speaking")
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._emit(t, "bot_stopped_speaking")

    def _first_sighting(self, frame) -> bool:
        if frame.id in self._seen_frame_ids:
            return False
        self._seen_frame_ids.add(frame.id)
        self._seen_frame_order.append(frame.id)
        if len(self._seen_frame_order) > 4096:
            self._seen_frame_ids.discard(self._seen_frame_order.popleft())
        return True

    def _emit(self, t: float, event_type: str, **fields):
        event = {"t": t, "type": event_type, **fields}
        self._file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        self._file.flush()

    def _flush_bot_response(self, t: float, *, interrupted: bool = False):
        text = "".join(self._bot_text)
        self._bot_text = []
        if not text:
            return
        event = {"text": text}
        if interrupted:
            event["interrupted"] = True
        self._emit(t, "bot_response", **event)

    async def _record_llm_run(self, t: float, context: LLMContext):
        messages = list(context.get_messages())
        # Identity comparison: context messages can be evicted mid-list (e.g.
        # by the screen share injector), so positional diffing is unreliable.
        new_indices = [
            i
            for i, m in enumerate(messages)
            if not any(m is prev for prev in self._prev_context_messages)
        ]
        self._prev_context_messages = messages

        stripped = await asyncio.to_thread(self._strip_messages, messages)
        self._emit(
            t,
            "llm_run",
            message_count=len(messages),
            new_messages=[stripped[i] for i in new_indices],
            messages=stripped,
        )

    async def _record_screen_frame(self, t: float, frame: InputImageRawFrame):
        def save() -> str:
            if frame.format and frame.format.startswith("image/"):
                return self._save_image(frame.image, frame.format)
            buffer = io.BytesIO()
            Image.frombytes(frame.format, frame.size, frame.image).save(buffer, format="JPEG")
            return self._save_image(buffer.getvalue(), "image/jpeg")

        path = await asyncio.to_thread(save)
        self._emit(t, "screen_frame", pts=frame.pts, size=list(frame.size), file=path)

    def _save_image(self, data: bytes, mime: str) -> str:
        digest = hashlib.sha1(data).hexdigest()[:16]
        filename = f"{digest}.{_MIME_EXTENSIONS.get(mime, 'bin')}"
        path = os.path.join(self._images_dir, filename)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
        return os.path.join("images", filename)

    def _strip_messages(self, messages: List[Any]) -> List[Any]:
        return [self._strip_message(m) for m in messages]

    def _strip_message(self, message: Any) -> Any:
        if isinstance(message, LLMSpecificMessage):
            return {"type": "llm_specific", "llm": message.llm, "message": repr(message.message)}
        if not isinstance(message, dict):
            return {"type": "unknown", "message": repr(message)}
        content = message.get("content")
        if not isinstance(content, list):
            return message
        stripped_content = []
        for item in content:
            url = item.get("image_url", {}).get("url", "") if isinstance(item, dict) else ""
            if url.startswith("data:"):
                mime, _, b64 = url.removeprefix("data:").partition(";base64,")
                path = self._save_image(base64.b64decode(b64), mime)
                item = {"type": "image_ref", "path": path, "mime": mime}
            stripped_content.append(item)
        return {**message, "content": stripped_content}
