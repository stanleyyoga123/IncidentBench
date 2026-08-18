from enum import StrEnum


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANUP_FAILED = "cleanup_failed"
    INTERRUPTED = "interrupted"
