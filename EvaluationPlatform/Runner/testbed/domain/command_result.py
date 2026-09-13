from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict:
        value = asdict(self)
        value["command"] = list(self.command)
        return value
