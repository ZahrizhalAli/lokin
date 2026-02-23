import sys

from lokin.services import DeprecatedModuleProxy

from .flux import *
from .stt import *
from .tts import *

sys.modules[__name__] = DeprecatedModuleProxy(globals(), "deepgram", "deepgram.[stt,tts]")
