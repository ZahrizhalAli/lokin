

"""Custom frame types for OpenAI Realtime API integration."""

import warnings

from lokin.services.openai.realtime.frames import *

with warnings.catch_warnings():
    warnings.simplefilter("always")
    warnings.warn(
        "Types in lokin.services.openai_realtime.frames are deprecated. "
        "Please use the equivalent types from "
        "lokin.services.openai.realtime.frames instead.",
        DeprecationWarning,
        stacklevel=2,
    )
