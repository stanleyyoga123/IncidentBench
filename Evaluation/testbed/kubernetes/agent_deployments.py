import json
import time
from pathlib import Path

from ..artifacts.artifact_layout import ArtifactLayout
from ..command.command_logger import CommandLogger
from ..constants import AGENT_DEPLOYMENTS
from .kubectl_client import KubectlClient


class AgentDeploymentController:
    def __init__(
        self,
        kubectl: KubectlClient,
        artifacts: ArtifactLayout,
        command_logger: CommandLogger,
        sleep=time.sleep,
    ) -> None:
        self.kubectl = kubectl
        self.artifacts = artifacts
        self.command_logger = command_logger
        self.sleep = sleep

    def scale(self, namespace: str, replicas: int, output_dir: Path | None = None) -> dict:
        destination = output_dir or self.artifacts.commands
        deployments = {}
        for deployment in AGENT_DEPLOYMENTS:
            result = self.kubectl.scale(deployment, namespace, replicas)
            deployments[deployment] = self.command_logger.write(
                result,
                destination,
                f"scale-{deployment}-{replicas}",
            )
        return {
            "namespace": namespace,
            "replicas": replicas,
            "deployments": deployments,
            "returncode": next(
                (
                    result["returncode"]
                    for result in deployments.values()
                    if result["returncode"] != 0
                ),
                0,
            ),
        }

    def wait(
        self,
        namespace: str,
        replicas: int,
        output_dir: Path | None = None,
        timeout_seconds: int = 300,
    ) -> dict:
        if replicas == 0:
            return self._wait_for_zero(namespace, output_dir, timeout_seconds)
        return self._wait_for_rollouts(namespace, output_dir)

    def _wait_for_zero(
        self,
        namespace: str,
        output_dir: Path | None,
        timeout_seconds: int,
    ) -> dict:
        destination = output_dir or self.artifacts.commands
        command = [
            "get",
            "deployment",
            *AGENT_DEPLOYMENTS,
            "-n",
            namespace,
            "-o",
            "json",
        ]
        stdout_parts = []
        stderr_parts = []
        deadline = time.monotonic() + timeout_seconds
        returncode = 1
        last_result = None
        while time.monotonic() < deadline:
            last_result = self.kubectl.run(command)
            stdout_parts.append(last_result.stdout)
            stderr_parts.append(last_result.stderr)
            if last_result.succeeded:
                try:
                    items = json.loads(last_result.stdout).get("items", [])
                except json.JSONDecodeError:
                    items = []
                if len(items) == len(AGENT_DEPLOYMENTS) and all(
                    item.get("spec", {}).get("replicas", 0) == 0
                    and item.get("status", {}).get("readyReplicas", 0) == 0
                    for item in items
                ):
                    returncode = 0
                    break
            self.sleep(5)
        destination.mkdir(parents=True, exist_ok=True)
        stdout_file = destination / "wait-agents-zero.stdout"
        stderr_file = destination / "wait-agents-zero.stderr"
        stdout_file.write_text("\n".join(stdout_parts))
        stderr_file.write_text("\n".join(stderr_parts))
        return {
            "command": ["kubectl", *command],
            "returncode": returncode,
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file),
        }

    def _wait_for_rollouts(self, namespace: str, output_dir: Path | None) -> dict:
        destination = output_dir or self.artifacts.commands
        stdout_parts = []
        stderr_parts = []
        returncode = 0
        failed_command = None
        for deployment in AGENT_DEPLOYMENTS:
            result = self.kubectl.rollout_status(
                f"deployment/{deployment}",
                namespace,
            )
            stdout_parts.append(f"$ {' '.join(result.command)}\n{result.stdout}")
            stderr_parts.append(f"$ {' '.join(result.command)}\n{result.stderr}")
            if not result.succeeded:
                returncode = result.returncode
                failed_command = list(result.command)
                break
        destination.mkdir(parents=True, exist_ok=True)
        stdout_file = destination / "agents-rollout-status.stdout"
        stderr_file = destination / "agents-rollout-status.stderr"
        stdout_file.write_text("\n".join(stdout_parts))
        stderr_file.write_text("\n".join(stderr_parts))
        return {
            "command": [
                "kubectl",
                "rollout",
                "status",
                "<agent-deployments>",
                "-n",
                namespace,
                "--timeout=10m",
            ],
            "failed_command": failed_command,
            "returncode": returncode,
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file),
        }
