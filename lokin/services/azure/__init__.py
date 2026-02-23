
import sys

from lokin.services import DeprecatedModuleProxy


sys.modules[__name__] = DeprecatedModuleProxy(globals(), "azure", "azure.[llm,stt,tts]")
