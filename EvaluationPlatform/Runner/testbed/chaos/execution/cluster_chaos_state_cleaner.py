from pathlib import Path

from ...command.command_logger import CommandLogger
from ...command.command_runner import CommandRunner


class ClusterChaosStateCleaner:
    """Run the repository's authoritative cluster and worker cleanup script."""

    def __init__(
        self,
        runner: CommandRunner,
        repo_root: Path,
        logger: CommandLogger,
        *,
        timeout_seconds: float = 900,
    ) -> None:
        self.runner = runner
        self.repo_root = repo_root
        self.logger = logger
        self.timeout_seconds = timeout_seconds
        self.script = repo_root / "scripts/cleanup_chaos_state.sh"

    def clean(self, output_dir: Path, name: str = "cleanup") -> dict:
        result = self.runner.run(
            ["bash", str(self.script), "--yes"],
            cwd=self.repo_root,
            timeout=self.timeout_seconds,
        )
        return self.logger.write(result, output_dir, name)
