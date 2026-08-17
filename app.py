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

from loguru import logger

print("🚀 Starting Lokin bot...")

logger.info("Loading Silero VAD model...")
from lokin.audio.vad.silero import SileroVADAnalyzer

logger.info("✅[Success] Silero VAD model loaded")

from lokin.frames.frames import LLMRunFrame

logger.info("Loading pipeline components...")
from lokin.observers.session_recorder import SessionRecorderObserver
from lokin.pipeline.pipeline import Pipeline
from lokin.pipeline.runner import PipelineRunner
from lokin.pipeline.task import PipelineParams, PipelineTask
from lokin.processors.aggregators.llm_context import LLMContext
from lokin.processors.screen_share_injector import ScreenShareContextInjector

from lokin.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from lokin.runner.types import RunnerArguments
from lokin.runner.utils import (create_transport, maybe_capture_participant_screen)
from lokin.services.cartesia.tts import CartesiaTTSService
from lokin.services.deepgram.stt import DeepgramSTTService
from lokin.services.openai.stt import OpenAISTTService
from lokin.services.elevenlabs.tts import ElevenLabsTTSService
from lokin.services.openai.tts import OpenAITTSService
from lokin.services.openai.llm import OpenAILLMService
from lokin.transports.base_transport import BaseTransport, TransportParams
from lokin.utils.system_prompt_parser import load_prompt
from lokin.utils.resume_parser import get_resume_text

logger.info("✅[Success] All components loaded successfully!")
from dotenv import load_dotenv

load_dotenv(override=True)

logger.info("Loading prompt...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, 'lokin/config', 'interviewer_prompt.md')

SYSTEM_PROMPT = load_prompt(PROMPT_PATH)
logger.info("✅[Success] Prompt Loaded")


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    # stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    stt = OpenAISTTService(api_key=os.getenv("OPENAI_API_KEY"))

    # tts = CartesiaTTSService(
    #     api_key=os.getenv("CARTESIA_API_KEY"),
    #     voice_id="86e30c1d-714b-4074-a1f2-1cb6b552fb49",  # Carson
    # )

    tts = OpenAITTSService(api_key=os.getenv("OPENAI_API_KEY"), speed=1.2)
    tts = ElevenLabsTTSService(api_key=os.getenv("ELEVEN"))
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))


    # Fold the candidate's uploaded resume (if any) into the system prompt so
    # the interviewer can tailor questions to their background.
    system_content = SYSTEM_PROMPT
    resume_text = get_resume_text()
    if resume_text:
        logger.info(f"Injecting candidate resume into system prompt ({len(resume_text)} chars)")
        system_content = (
            f"{SYSTEM_PROMPT}\n\n"
            "# Candidate Resume\n"
            "The following is the candidate's resume. Use it to tailor your "
            "questions to their background and experience.\n\n"
            f"{resume_text}"
        )

    # Build Messages Template
    messages = [
        {
            "role": "system",
            "content": system_content,
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

    recorder = SessionRecorderObserver()
    logger.info(f"Recording session to {recorder.session_dir}")

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[recorder],
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
