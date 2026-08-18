import subprocess
from collections.abc import Callable
from pathlib import Path

from ..domain.command_result import CommandResult


class CommandRunner:
    def __init__(self, run_function: Callable = subprocess.run) -> None:
        self._run_function = run_function

    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        try:
            completed = self._run_function(
                command,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=tuple(command),
                returncode=124,
                stdout=self._decode(exc.stdout),
                stderr=self._decode(exc.stderr) + f"command timed out after {timeout}s\n",
                timed_out=True,
            )
        return CommandResult(
            command=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _decode(value: str | bytes | None) -> str:
        if value is None:
            return ""
        return value.decode(errors="replace") if isinstance(value, bytes) else value
