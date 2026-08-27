import json
from pathlib import Path

from ..command.command_runner import CommandRunner
from ..domain.chaos_schedule import ChaosSchedule
from ..domain.command_result import CommandResult


class ChaosScheduleClient:
    RECORDS_FINALIZER = "chaos-mesh/records"
    DESTROYED_EXPERIMENT_ERRORS = (
        "can not recover destroyed experiment",
        "cannot recover destroyed experiment",
    )
    EXPERIMENT_RESOURCES = (
        "schedules.chaos-mesh.org",
        "workflows.chaos-mesh.org",
        "workflownodes.chaos-mesh.org",
        "awschaos.chaos-mesh.org",
        "azurechaos.chaos-mesh.org",
        "blockchaos.chaos-mesh.org",
        "dnschaos.chaos-mesh.org",
        "gcpchaos.chaos-mesh.org",
        "httpchaos.chaos-mesh.org",
        "iochaos.chaos-mesh.org",
        "jvmchaos.chaos-mesh.org",
        "kernelchaos.chaos-mesh.org",
        "networkchaos.chaos-mesh.org",
        "physicalmachinechaos.chaos-mesh.org",
        "podchaos.chaos-mesh.org",
        "podhttpchaos.chaos-mesh.org",
        "podiochaos.chaos-mesh.org",
        "podnetworkchaos.chaos-mesh.org",
        "statuschecks.chaos-mesh.org",
        "stresschaos.chaos-mesh.org",
        "timechaos.chaos-mesh.org",
    )

    def __init__(
        self,
        runner: CommandRunner,
        repo_root: Path,
        manifest_paths: dict[str, Path] | None = None,
    ) -> None:
        self.runner = runner
        self.repo_root = Path(repo_root)
        self.manifest_paths = manifest_paths or {}

    def apply(self, schedule: ChaosSchedule) -> CommandResult:
        return self._run(
            ["kubectl", "apply", "-f", str(self._path(schedule))],
            timeout=120,
        )

    def delete(self, schedule: ChaosSchedule) -> CommandResult:
        return self._run(
            [
                "kubectl",
                "delete",
                "-f",
                str(self._path(schedule)),
                "--ignore-not-found",
                "--cascade=background",
                "--wait=true",
            ],
            timeout=240,
        )

    def get(self, schedule: ChaosSchedule) -> CommandResult:
        return self._run(
            [
                "kubectl",
                "get",
                "schedule",
                schedule.name,
                "-n",
                schedule.namespace,
                "-o",
                "name",
                "--ignore-not-found",
            ],
            timeout=30,
        )

    def get_children(self, schedule: ChaosSchedule) -> CommandResult:
        return self._run(
            [
                "kubectl",
                "get",
                schedule.child_type,
                "-n",
                schedule.namespace,
                f"--selector=managed-by={schedule.name}",
                "-o",
                "name",
                "--ignore-not-found",
            ],
            timeout=30,
        )

    def delete_all_experiments(self) -> dict[str, CommandResult]:
        return {
            resource: self._run(
                [
                    "kubectl",
                    "delete",
                    resource,
                    "--all",
                    "--all-namespaces",
                    "--ignore-not-found",
                    "--wait=true",
                    "--timeout=240s",
                ],
                timeout=300,
            )
            for resource in self.EXPERIMENT_RESOURCES
        }

    def recover_destroyed_experiment_finalizers(
        self,
    ) -> dict[str, CommandResult]:
        """Release only terminating records whose underlying fault is recovered.

        Chaos Mesh can leave a child experiment indefinitely terminating when
        its controller retries recovery after chaosd has already destroyed the
        experiment. Removing the records finalizer is safe only with explicit
        recovery evidence and when no unrelated finalizer is present.
        """
        resources = ",".join(self.EXPERIMENT_RESOURCES)
        scan = self._run(
            [
                "kubectl",
                "get",
                resources,
                "--all-namespaces",
                "--ignore-not-found",
                "-o",
                "json",
            ],
            timeout=60,
        )
        results = {"scan": scan}
        if not scan.succeeded:
            return results
        if not scan.stdout.strip():
            return results
        try:
            body = json.loads(scan.stdout)
        except json.JSONDecodeError as exc:
            results["scan"] = CommandResult(
                command=scan.command,
                returncode=1,
                stdout=scan.stdout,
                stderr=scan.stderr + f"invalid Chaos Mesh resource JSON: {exc}\n",
            )
            return results

        items = body.get("items", []) if isinstance(body, dict) else []
        for item in items if isinstance(items, list) else []:
            if not self._safe_to_release_records_finalizer(item):
                continue
            metadata = item["metadata"]
            kind = item.get("kind")
            namespace = metadata.get("namespace")
            name = metadata.get("name")
            identity = f"{namespace}/{kind}/{name}"
            results[identity] = self._run(
                [
                    "kubectl",
                    "patch",
                    str(kind),
                    str(name),
                    "-n",
                    str(namespace),
                    "--type=merge",
                    "-p",
                    '{"metadata":{"finalizers":[]}}',
                ],
                timeout=30,
            )
        return results

    @classmethod
    def _safe_to_release_records_finalizer(cls, item: object) -> bool:
        if not isinstance(item, dict):
            return False
        metadata = item.get("metadata")
        if not isinstance(metadata, dict) or not metadata.get("deletionTimestamp"):
            return False
        finalizers = metadata.get("finalizers")
        if not isinstance(finalizers, list) or set(finalizers) != {
            cls.RECORDS_FINALIZER
        }:
            return False
        if not all(
            isinstance(metadata.get(field), str) and metadata.get(field)
            for field in ("namespace", "name")
        ) or not isinstance(item.get("kind"), str):
            return False
        status = item.get("status")
        serialized_status = json.dumps(status, ensure_ascii=False).lower()
        if any(message in serialized_status for message in cls.DESTROYED_EXPERIMENT_ERRORS):
            return True
        conditions = status.get("conditions", []) if isinstance(status, dict) else []
        return any(
            isinstance(condition, dict)
            and condition.get("type") == "AllRecovered"
            and str(condition.get("status")).lower() == "true"
            for condition in conditions
        )

    def _run(self, command: list[str], timeout: int) -> CommandResult:
        return self.runner.run(command, cwd=self.repo_root, timeout=timeout)

    def _path(self, schedule: ChaosSchedule) -> Path:
        return self.manifest_paths.get(schedule.reference, schedule.source_path)
