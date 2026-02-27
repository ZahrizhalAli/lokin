import sys

from lokin.services import DeprecatedModuleProxy

from .stt import *
from .tts import *

sys.modules[__name__] = DeprecatedModuleProxy(globals(), "elevenlabs", "elevenlabs.[stt,tts]")
