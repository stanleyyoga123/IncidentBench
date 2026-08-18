import json
from datetime import datetime, timezone
from pathlib import Path

from ..command.command_runner import CommandRunner
from .prometheus.client import PrometheusClient
from .prometheus.query_catalog import QueryCatalog
from .snapshot_command_catalog import SnapshotCommandCatalog


class SnapshotCollector:
    def __init__(
        self,
        output_dir: Path,
        namespace: str,
        command_runner: CommandRunner,
        prometheus: PrometheusClient,
        queries: QueryCatalog,
    ) -> None:
        self.output_dir = output_dir
        self.namespace = namespace
        self.command_runner = command_runner
        self.prometheus = prometheus
        self.queries = queries

    def collect(self, label: str) -> dict:
        destination = self.output_dir / "snapshots" / label
        destination.mkdir(parents=True, exist_ok=True)
        commands = []
        for name, command in SnapshotCommandCatalog(self.namespace).commands():
            result = self.command_runner.run(command)
            stdout_file, stderr_file = f"{name}.out", f"{name}.err"
            (destination / stdout_file).write_text(result.stdout)
            (destination / stderr_file).write_text(result.stderr)
            commands.append(
                {
                    "name": name,
                    "command": command,
                    "returncode": result.returncode,
                    "stdout_file": stdout_file,
                    "stderr_file": stderr_file,
                }
            )
        prometheus = self._collect_prometheus(destination)
        metadata = {
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "namespace": self.namespace,
            "commands": commands,
            "prometheus": prometheus,
        }
        (destination / "snapshot.json").write_text(json.dumps(metadata, indent=2))
        return metadata

    def _collect_prometheus(self, destination: Path) -> dict:
        if not self.prometheus.enabled:
            return {"enabled": False, "reason": "no prometheus url supplied"}
        output = destination / "prometheus"
        output.mkdir(parents=True, exist_ok=True)
        results = {"enabled": True, "queries": []}
        for name, expression in self.queries.snapshot_queries().items():
            entry = {"name": name, "query": expression, "ok": False, "output_file": f"{name}.json"}
            try:
                entry["url"], body = self.prometheus.query(expression)
                entry["ok"] = True
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, indent=2)
                entry["error"] = str(exc)
            (output / entry["output_file"]).write_text(body)
            results["queries"].append(entry)
        return results
