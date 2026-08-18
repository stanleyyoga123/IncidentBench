from dataclasses import dataclass, field

from .run_status import RunStatus


@dataclass(frozen=True)
class PhaseResult:
    name: str
    status: RunStatus = RunStatus.COMPLETED
    returncode: int = 0
    details: dict = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status not in {RunStatus.COMPLETED}

    @classmethod
    def success(cls, name: str, **details) -> "PhaseResult":
        return cls(name=name, details=details)

    @classmethod
    def failure(
        cls,
        name: str,
        returncode: int = 1,
        status: RunStatus = RunStatus.FAILED,
        **details,
    ) -> "PhaseResult":
        return cls(
            name=name,
            status=status,
            returncode=returncode,
            details=details,
        )
