import sys

from lokin.services import DeprecatedModuleProxy

from .base_stt import *
from .stt import *

sys.modules[__name__] = DeprecatedModuleProxy(globals(), "whisper", "whisper.stt")
