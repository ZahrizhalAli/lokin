"""Lokin Quickstart.

The example runs a simple voice AI bot that you can connect to using your
browser and speak with it.

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run the bot using::

    uv run bot.py
"""

import os

from dotenv import load_dotenv
from loguru import logger

print("🚀 Starting Pipecat bot...")
print("⏳ Loading models and imports (20 seconds, first run only)\n")

logger.info("Loading Silero VAD model...")
from lokin.audio.vad.silero import SileroVADAnalyzer

logger.info("✅ Silero VAD model loaded")

from lokin.frames.frames import LLMRunFrame

logger.info("Loading pipeline components...")
from lokin.pipeline.pipeline import Pipeline
from lokin.pipeline.runner import PipelineRunner
from lokin.pipeline.task import PipelineParams, PipelineTask
from lokin.processors.aggregators.llm_context import LLMContext

from lokin.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from lokin.runner.types import RunnerArguments
from lokin.runner.utils import create_transport
from lokin.services.cartesia.tts import CartesiaTTSService
from lokin.services.deepgram.stt import DeepgramSTTService
from lokin.services.openai.llm import OpenAILLMService
from lokin.transports.base_transport import BaseTransport, TransportParams
from lokin.transports.daily.transport import DailyParams

logger.info("✅ All components loaded successfully!")