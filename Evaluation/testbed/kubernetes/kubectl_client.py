from pathlib import Path

from ..command.command_runner import CommandRunner
from ..domain.command_result import CommandResult


class KubectlClient:
    def __init__(self, runner: CommandRunner, repo_root: Path) -> None:
        self.runner = runner
        self.repo_root = repo_root

    def run(self, arguments: list[str], timeout: float | None = None) -> CommandResult:
        return self.runner.run(
            ["kubectl", *arguments],
            cwd=self.repo_root,
            timeout=timeout,
        )

    def scale(self, deployment: str, namespace: str, replicas: int) -> CommandResult:
        return self.run(
            [
                "scale",
                "deployment",
                deployment,
                "-n",
                namespace,
                f"--replicas={replicas}",
            ]
        )

    def rollout_status(
        self,
        deployment: str,
        namespace: str,
        timeout: str = "10m",
    ) -> CommandResult:
        return self.run(
            [
                "rollout",
                "status",
                deployment,
                "-n",
                namespace,
                f"--timeout={timeout}",
            ]
        )
