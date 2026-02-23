
import sys

from lokin.services import DeprecatedModuleProxy

from .image import *
from .llm import *
from .realtime import *
from .stt import *
from .tts import *

sys.modules[__name__] = DeprecatedModuleProxy(globals(), "openai", "openai.[image,llm,stt,tts]")
