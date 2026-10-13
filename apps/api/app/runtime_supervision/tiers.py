from enum import IntEnum


class ExecutionTier(IntEnum):
    ROOT = 0
    PRIVILEGED = 1
    STANDARD = 2
    SANDBOX = 3
