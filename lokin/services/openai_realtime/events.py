
"""Event models and data structures for OpenAI Realtime API communication."""

import warnings

from lokin.services.openai.realtime.events import *

with warnings.catch_warnings():
    warnings.simplefilter("always")
    warnings.warn(
        "Types in pipecat.services.openai_realtime.events are deprecated. "
        "Please use the equivalent types from "
        "pipecat.services.openai.realtime.events instead.",
        DeprecationWarning,
        stacklevel=2,
    )
