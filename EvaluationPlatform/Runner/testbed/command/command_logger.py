from pathlib import Path

from ..domain.command_result import CommandResult


class CommandLogger:
    def write(self, result: CommandResult, output_dir: Path, name: str) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_file = output_dir / f"{name}.stdout"
        stderr_file = output_dir / f"{name}.stderr"
        stdout_file.write_text(result.stdout)
        stderr_file.write_text(result.stderr)
        return {
            "command": list(result.command),
            "returncode": result.returncode,
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file),
            "timed_out": result.timed_out,
        }
