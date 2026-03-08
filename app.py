"""Lokin Quickstart.

The example runs a simple voice AI bot that you can connect to using your
browser and speak with it.

Required AI services:
- Deepgram (Speech-to-Text) (Optional)
- OpenAI (LLM)
- Cartesia (Text-to-Speech) (Optional)

Run the bot using::
    uv run app.py
"""

import os
import time

from loguru import logger

print("🚀 Starting Lokin bot...")

logger.info("Loading Silero VAD model...")
from lokin.audio.vad.silero import SileroVADAnalyzer

logger.info("✅[Success] Silero VAD model loaded")

from lokin.frames.frames import InputImageRawFrame, LLMContextFrame, LLMRunFrame

logger.info("Loading pipeline components...")
from lokin.pipeline.pipeline import Pipeline
from lokin.pipeline.runner import PipelineRunner
from lokin.pipeline.task import PipelineParams, PipelineTask
from lokin.processors.aggregators.llm_context import LLMContext
from lokin.processors.frame_processor import FrameDirection, FrameProcessor

from lokin.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from lokin.runner.types import RunnerArguments
from lokin.runner.utils import (create_transport, maybe_capture_participant_screen)
from lokin.services.cartesia.tts import CartesiaTTSService
from lokin.services.deepgram.stt import DeepgramSTTService
from lokin.services.openai.stt import OpenAISTTService
from lokin.services.openai.tts import OpenAITTSService
from lokin.services.openai.llm import OpenAILLMService
from lokin.transports.base_transport import BaseTransport, TransportParams

logger.info("✅[Success] All components loaded successfully!")
from dotenv import load_dotenv

load_dotenv(override=True)

class ScreenShareContextInjector(FrameProcessor):
    """Inject the latest screen share frame into the LLM context."""

    def __init__(self, *, min_interval_secs: float = 1.5):
        super().__init__(name="ScreenShareContextInjector")
        self._latest_frame: InputImageRawFrame | None = None
        self._latest_frame_time: float = 0.0
        self._last_injected_pts: int | None = None
        self._min_interval_secs = min_interval_secs
        self._last_injected_time: float = 0.0

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputImageRawFrame) and frame.transport_source == "screenVideo":
            self._latest_frame = frame
            self._latest_frame_time = time.monotonic()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMContextFrame):
            await self._maybe_inject_screen(frame)
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)

    async def _maybe_inject_screen(self, frame: LLMContextFrame):
        if not self._latest_frame:
            return

        if self._last_injected_pts == self._latest_frame.pts:
            return

        now = time.monotonic()
        if now - self._latest_frame_time > 5:
            return

        if now - self._last_injected_time < self._min_interval_secs:
            return

        await frame.context.add_image_frame_message(
            format=self._latest_frame.format,
            size=self._latest_frame.size,
            image=self._latest_frame.image,
            text="User screen share",
        )

        self._last_injected_pts = self._latest_frame.pts
        self._last_injected_time = now


SYSTEM_PROMPT = """
You are Carson, a senior AI engineer specializing in practical machine learning implementation and AI integration for production applications. 
Your expertise spans large language models, RLHF, and intelligent automation. 
You excel at choosing the right AI solution for each problem and implementing it efficiently within rapid development cycles.

You will be my interviewer and given the question on the screen you will ask me to write code solution in Python.
"""

async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    # stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    stt = OpenAISTTService(api_key=os.getenv("OPENAI_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="86e30c1d-714b-4074-a1f2-1cb6b552fb49",  # Carson
    )

    # tts = OpenAITTSService(api_key=os.getenv("OPENAI_API_KEY"), speed=1.2)


    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # Build Messages Template
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
    ]

    context = LLMContext(messages)

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_idle_timeout=5.0
        ),
    )

    screen_injector = ScreenShareContextInjector()

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            user_aggregator,  # User responses
            screen_injector,  # Inject latest screen share into LLM context
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        await maybe_capture_participant_screen(transport, client, framerate=1)


        # Kick off the conversation.
        messages.append({"role": "system", "content": "Say hello and briefly introduce yourself."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot called by the runner."""

    # Create transport params : WebRTC
    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=True
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    # Run Bot
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from lokin.runner.run import main

    main()
