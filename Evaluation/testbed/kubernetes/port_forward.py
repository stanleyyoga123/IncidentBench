import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from ..artifacts.artifact_layout import ArtifactLayout


class PortForwardController:
    def __init__(
        self,
        repo_root: Path,
        artifacts: ArtifactLayout,
        popen: Callable = subprocess.Popen,
        sleep=time.sleep,
    ) -> None:
        self.repo_root = repo_root
        self.artifacts = artifacts
        self.popen = popen
        self.sleep = sleep

    @staticmethod
    def is_local_port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def start(
        self,
        namespace: str,
        local_port: int,
        remote_port: int = 80,
        timeout_seconds: int = 30,
    ) -> tuple[object | None, dict]:
        output_dir = self.artifacts.commands
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_file = output_dir / "port-forward-frontend.stdout"
        stderr_file = output_dir / "port-forward-frontend.stderr"
        command = [
            "kubectl",
            "port-forward",
            "svc/frontend",
            f"{local_port}:{remote_port}",
            "-n",
            namespace,
        ]
        if self.is_local_port_open(local_port):
            stdout_file.write_text(f"localhost:{local_port} is already accepting connections\n")
            stderr_file.write_text("")
            return None, self._result(command, 0, True, stdout_file, stderr_file)
        stdout_handle = stdout_file.open("w")
        stderr_handle = stderr_file.open("w")
        process = self.popen(
            command,
            cwd=self.repo_root,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        stdout_handle.close()
        stderr_handle.close()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            returncode = process.poll()
            if returncode is not None:
                return process, self._result(
                    command, returncode, False, stdout_file, stderr_file
                )
            if self.is_local_port_open(local_port):
                return process, self._result(command, 0, False, stdout_file, stderr_file)
            self.sleep(1)
        return process, self._result(command, 1, False, stdout_file, stderr_file)

    @staticmethod
    def _result(command, returncode, already_running, stdout_file, stderr_file):
        return {
            "command": command,
            "returncode": returncode,
            "already_running": already_running,
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file),
        }
