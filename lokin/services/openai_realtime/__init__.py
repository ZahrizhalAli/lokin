
import warnings

from lokin.services.azure.realtime.llm import AzureRealtimeLLMService
from lokin.services.openai.realtime.events import (
    InputAudioNoiseReduction,
    InputAudioTranscription,
    SemanticTurnDetection,
    SessionProperties,
    TurnDetection,
)
from lokin.services.openai.realtime.llm import OpenAIRealtimeLLMService

with warnings.catch_warnings():
    warnings.simplefilter("always")
    warnings.warn(
        "Types in pipecat.services.openai_realtime are deprecated. "
        "Please use the equivalent types from "
        "pipecat.services.openai.realtime instead.",
        DeprecationWarning,
        stacklevel=2,
    )

__all__ = [
    "AzureRealtimeLLMService",
    "InputAudioNoiseReduction",
    "InputAudioTranscription",
    "SemanticTurnDetection",
    "SessionProperties",
    "TurnDetection",
    "OpenAIRealtimeLLMService",
]
