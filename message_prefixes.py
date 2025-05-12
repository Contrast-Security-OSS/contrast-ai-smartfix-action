from enum import Enum

class MessagePrefix(Enum):
    CONFIG_INVALID = "CONFIG_INVALID: "
    INFO = "INFO: "
    WARNING = "WARNING: " # Adding a warning prefix as it's used in version_check.py
