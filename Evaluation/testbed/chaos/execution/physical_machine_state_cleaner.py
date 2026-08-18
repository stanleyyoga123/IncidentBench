import os
import shlex
from pathlib import Path

from ...command.command_logger import CommandLogger
from ...command.command_runner import CommandRunner
from ...constants import NODE_INVENTORY_PATH
from ...domain.chaos_schedule import ChaosSchedule


class PhysicalMachineStateCleaner:
    """Remove and verify host-level state that can outlive Chaos Mesh CRs."""

    REMOTE_CLEANUP_SCRIPT = (
        "set -eu\n"
        "sudo -n /usr/local/sbin/evaluation-clean-host-chaos"
    )

    def __init__(
        self,
        runner: CommandRunner,
        repo_root: Path,
        logger: CommandLogger,
        *,
        inventory_path: Path | None = None,
        ssh_user: str | None = None,
        ssh_identity_file: Path | None = None,
        ssh_known_hosts_file: Path | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.runner = runner
        self.repo_root = Path(repo_root)
        self.logger = logger
        self.inventory_path = inventory_path or NODE_INVENTORY_PATH
        self.ssh_user = ssh_user or os.getenv(
            "CHAOS_NODE_SSH_USER",
            "chaos-cleaner",
        )
        identity_file = ssh_identity_file or os.getenv(
            "CHAOS_NODE_SSH_IDENTITY_FILE"
        )
        known_hosts_file = ssh_known_hosts_file or os.getenv(
            "CHAOS_NODE_SSH_KNOWN_HOSTS_FILE"
        )
        self.ssh_identity_file = (
            str(identity_file) if identity_file is not None else None
        )
        self.ssh_known_hosts_file = (
            str(known_hosts_file) if known_hosts_file is not None else None
        )
        self.timeout_seconds = timeout_seconds
        self.hosts = self._load_hosts()

    def clean_all(self, output_dir: Path, prefix: str = "startup") -> dict:
        return self._clean(tuple(self.hosts), output_dir, prefix)

    def clean_schedule(
        self,
        schedule: ChaosSchedule,
        output_dir: Path,
        prefix: str,
    ) -> dict:
        targets = self._schedule_targets(schedule)
        if not targets:
            return {
                "required": False,
                "returncode": 0,
                "nodes": {},
            }
        return self._clean(targets, output_dir, prefix)

    def _clean(
        self,
        targets: tuple[str, ...],
        output_dir: Path,
        prefix: str,
    ) -> dict:
        nodes = {}
        failed = False
        for node in targets:
            address = self.hosts.get(node)
            if address is None:
                nodes[node] = {
                    "returncode": 1,
                    "error": f"unknown physical machine target: {node}",
                }
                failed = True
                continue
            command = [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "StrictHostKeyChecking=yes",
            ]
            if self.ssh_identity_file is not None:
                command.extend(["-i", self.ssh_identity_file])
            if self.ssh_known_hosts_file is not None:
                command.extend(
                    [
                        "-o",
                        f"UserKnownHostsFile={self.ssh_known_hosts_file}",
                    ]
                )
            command.extend(
                [
                    f"{self.ssh_user}@{address}",
                    self.REMOTE_CLEANUP_SCRIPT,
                ]
            )
            result = self.runner.run(
                command,
                cwd=self.repo_root,
                timeout=self.timeout_seconds,
            )
            nodes[node] = self.logger.write(
                result,
                output_dir,
                f"{prefix}-{node}",
            )
            failed |= not result.succeeded
        return {
            "required": True,
            "returncode": 1 if failed else 0,
            "nodes": nodes,
        }

    def _load_hosts(self) -> dict[str, str]:
        try:
            lines = self.inventory_path.read_text().splitlines()
        except OSError as exc:
            raise ValueError(
                f"cannot read service-node inventory {self.inventory_path}: {exc}"
            ) from exc

        section = None
        resolved = {}
        for raw_line in lines:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()
                continue
            if section != "service_nodes":
                continue
            try:
                parts = shlex.split(line)
            except ValueError as exc:
                raise ValueError(
                    f"invalid service-node inventory {self.inventory_path}: {exc}"
                ) from exc
            if not parts:
                continue
            variables = dict(
                part.split("=", 1) for part in parts[1:] if "=" in part
            )
            address = variables.get("ansible_host")
            if not address:
                raise ValueError(
                    f"service-node inventory {self.inventory_path} has an invalid host"
                )
            resolved[parts[0]] = address

        if not resolved:
            raise ValueError(
                f"service-node inventory {self.inventory_path} has no hosts"
            )
        return resolved

    @staticmethod
    def _schedule_targets(schedule: ChaosSchedule) -> tuple[str, ...]:
        child = schedule.manifest["spec"][schedule.child_key]
        selector = child.get("selector", {})
        if schedule.child_type == "PhysicalMachineChaos":
            selected = selector.get("physicalMachines", {})
            if not isinstance(selected, dict):
                return ()
            return tuple(
                dict.fromkeys(
                    node
                    for nodes in selected.values()
                    if isinstance(nodes, list)
                    for node in nodes
                    if isinstance(node, str)
                )
            )
        nodes = selector.get("nodes", [])
        if not isinstance(nodes, list):
            return ()
        return tuple(dict.fromkeys(node for node in nodes if isinstance(node, str)))
