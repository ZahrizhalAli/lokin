

"""Azure OpenAI Realtime LLM service implementation."""

import warnings

from lokin.services.azure.realtime.llm import *

with warnings.catch_warnings():
    warnings.simplefilter("always")
    warnings.warn(
        "Types in lokin.services.openai_realtime.azure are deprecated. "
        "Please use the equivalent types from "
        "lokin.services.azure.realtime.llm instead.",
        DeprecationWarning,
        stacklevel=2,
    )
