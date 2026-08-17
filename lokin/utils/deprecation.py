import re

from typing_extensions import deprecated

__all__ = ["DEPRECATION_MESSAGE_RE", "deprecated"]

DEPRECATION_MESSAGE_RE = re.compile(
    r"^`(?P<subject>[^`]+)` is deprecated since (?P<version>\d+\.\d+\.\d+) "
    r"and will be removed in (?P<removal>\d+\.\d+\.\d+)\. "
    r"(?:Use (?P<replacement>.+) instead\.|No replacement\.)"
)