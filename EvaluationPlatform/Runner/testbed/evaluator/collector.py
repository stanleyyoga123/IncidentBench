import json
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_QUERY_PARAMS = {
    "service": ".+",
    "namespace": ".+",
    "node": ".+",
    "quantile": "0.95",
    "rate_window": "1m",
    "reporter": "destination",
}


PROMETHEUS_QUERIES = {
    "deployment_cpu_usage": (
        "sum by (namespace, deployment) ("
        "rate(container_cpu_usage_seconds_total{{"
        'namespace=~"{namespace}", container!="", container!="POD"'
        "}}[{rate_window}])"
        " * on (namespace, pod) group_left(replicaset) "
        "label_replace(kube_pod_owner{{"
        'namespace=~"{namespace}", owner_kind="ReplicaSet"'
        '}}, "replicaset", "$1", "owner_name", "(.*)")'
        " * on (namespace, replicaset) group_left(deployment) "
        "label_replace(kube_replicaset_owner{{"
        'namespace=~"{namespace}", owner_kind="Deployment", owner_name=~"{service}"'
        '}}, "deployment", "$1", "owner_name", "(.*)")'
        ")"
    ),
    "deployment_cpu_request_utilization_percent": (
        "100 * ("
        "sum by (namespace, deployment) ("
        "rate(container_cpu_usage_seconds_total{{"
        'namespace=~"{namespace}", container!="", container!="POD"'
        "}}[{rate_window}])"
        " * on (namespace, pod) group_left(replicaset) "
        "label_replace(kube_pod_owner{{"
        'namespace=~"{namespace}", owner_kind="ReplicaSet"'
        '}}, "replicaset", "$1", "owner_name", "(.*)")'
        " * on (namespace, replicaset) group_left(deployment) "
        "label_replace(kube_replicaset_owner{{"
        'namespace=~"{namespace}", owner_kind="Deployment", owner_name=~"{service}"'
        '}}, "deployment", "$1", "owner_name", "(.*)")'
        ")"
        " / "
        "sum by (namespace, deployment) ("
        "kube_pod_container_resource_requests{{"
        'namespace=~"{namespace}", resource="cpu", unit="core"'
        "}}"
        " * on (namespace, pod) group_left(replicaset) "
        "label_replace(kube_pod_owner{{"
        'namespace=~"{namespace}", owner_kind="ReplicaSet"'
        '}}, "replicaset", "$1", "owner_name", "(.*)")'
        " * on (namespace, replicaset) group_left(deployment) "
        "label_replace(kube_replicaset_owner{{"
        'namespace=~"{namespace}", owner_kind="Deployment", owner_name=~"{service}"'
        '}}, "deployment", "$1", "owner_name", "(.*)")'
        ")"
        ")"
    ),
    "deployment_memory_request_utilization_percent": (
        "100 * ("
        "sum by (namespace, deployment) ("
        "container_memory_working_set_bytes{{"
        'namespace=~"{namespace}", container!="", container!="POD"'
        "}}"
        " * on (namespace, pod) group_left(replicaset) "
        "label_replace(kube_pod_owner{{"
        'namespace=~"{namespace}", owner_kind="ReplicaSet"'
        '}}, "replicaset", "$1", "owner_name", "(.*)")'
        " * on (namespace, replicaset) group_left(deployment) "
        "label_replace(kube_replicaset_owner{{"
        'namespace=~"{namespace}", owner_kind="Deployment", owner_name=~"{service}"'
        '}}, "deployment", "$1", "owner_name", "(.*)")'
        ")"
        " / "
        "sum by (namespace, deployment) ("
        "kube_pod_container_resource_requests{{"
        'namespace=~"{namespace}", resource="memory", unit="byte"'
        "}}"
        " * on (namespace, pod) group_left(replicaset) "
        "label_replace(kube_pod_owner{{"
        'namespace=~"{namespace}", owner_kind="ReplicaSet"'
        '}}, "replicaset", "$1", "owner_name", "(.*)")'
        " * on (namespace, replicaset) group_left(deployment) "
        "label_replace(kube_replicaset_owner{{"
        'namespace=~"{namespace}", owner_kind="Deployment", owner_name=~"{service}"'
        '}}, "deployment", "$1", "owner_name", "(.*)")'
        ")"
        ")"
    ),
    "deployment_disk_io_bytes_per_second": (
        "sum by (namespace, deployment) ("
        "("
        "rate(container_fs_reads_bytes_total{{"
        'namespace=~"{namespace}", container!="", container!="POD"'
        "}}[{rate_window}])"
        " + "
        "rate(container_fs_writes_bytes_total{{"
        'namespace=~"{namespace}", container!="", container!="POD"'
        "}}[{rate_window}])"
        ")"
        " * on (namespace, pod) group_left(replicaset) "
        "label_replace(kube_pod_owner{{"
        'namespace=~"{namespace}", owner_kind="ReplicaSet"'
        '}}, "replicaset", "$1", "owner_name", "(.*)")'
        " * on (namespace, replicaset) group_left(deployment) "
        "label_replace(kube_replicaset_owner{{"
        'namespace=~"{namespace}", owner_kind="Deployment", owner_name=~"{service}"'
        '}}, "deployment", "$1", "owner_name", "(.*)")'
        ")"
    ),
    "deployment_network_io_bytes_per_second": (
        "sum by (destination_workload_namespace, destination_workload) ("
        "rate(istio_request_bytes_sum{{"
        'reporter=~"{reporter}", '
        'destination_workload_namespace=~"{namespace}", '
        'destination_workload=~"{service}"'
        "}}[{rate_window}])"
        " + "
        "rate(istio_response_bytes_sum{{"
        'reporter=~"{reporter}", '
        'destination_workload_namespace=~"{namespace}", '
        'destination_workload=~"{service}"'
        "}}[{rate_window}])"
        ")"
    ),
    "node_cpu_utilization_percent": (
        "100 * ("
        "1 - avg by (node) ("
        "rate(node_cpu_seconds_total{{"
        'node=~"{node}", mode="idle"'
        "}}[{rate_window}])"
        ")"
        ")"
    ),
    "node_memory_utilization_percent": (
        "100 * ("
        "1 - ("
        'node_memory_MemAvailable_bytes{{node=~"{node}"}}'
        " / "
        'node_memory_MemTotal_bytes{{node=~"{node}"}}'
        ")"
        ")"
    ),
    "node_disk_io_bytes_per_second": (
        "sum by (node) ("
        "rate(node_disk_read_bytes_total{{"
        'node=~"{node}", device=~".+"'
        "}}[{rate_window}])"
        " + "
        "rate(node_disk_written_bytes_total{{"
        'node=~"{node}", device=~".+"'
        "}}[{rate_window}])"
        ")"
    ),
    "node_network_io_bytes_per_second": (
        "sum by (node) ("
        "rate(node_network_receive_bytes_total{{"
        'node=~"{node}", device!="lo"'
        "}}[{rate_window}])"
        " + "
        "rate(node_network_transmit_bytes_total{{"
        'node=~"{node}", device!="lo"'
        "}}[{rate_window}])"
        ")"
    ),
    "app_instance_count": (
        "kube_deployment_spec_replicas{{"
        'namespace=~"{namespace}", deployment=~"{service}"'
        "}}"
    ),
    "traffic_rps": (
        "sum by (destination_workload_namespace, destination_workload) ("
        "rate(istio_requests_total{{"
        'reporter=~"{reporter}", '
        'destination_workload_namespace=~"{namespace}", '
        'destination_workload=~"{service}"'
        "}}[{rate_window}])"
        ")"
    ),
    "response_time_p95_seconds": (
        "("
        "histogram_quantile({quantile}, "
        "sum by (le, destination_workload_namespace, destination_workload) ("
        "rate(istio_request_duration_milliseconds_bucket{{"
        'reporter=~"{reporter}", '
        'destination_workload_namespace=~"{namespace}", '
        'destination_workload=~"{service}"'
        "}}[{rate_window}])"
        "))"
        " / 1000"
        ")"
    ),
    "http_5xx_rate": (
        "sum by (destination_workload_namespace, destination_workload) ("
        "rate(istio_requests_total{{"
        'reporter=~"{reporter}", '
        'destination_workload_namespace=~"{namespace}", '
        'destination_workload=~"{service}", '
        'response_code=~"5.*"'
        "}}[{rate_window}])"
        ")"
    ),
}


@dataclass
class SnapshotCommand:
    name: str
    command: list[str]
    returncode: int
    stdout_file: str
    stderr_file: str


class Evaluator:
    def __init__(
        self,
        output_dir: Path,
        namespace: str = "online-boutique",
        prometheus_url: str | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.namespace = namespace
        self.prometheus_url = prometheus_url.rstrip("/") if prometheus_url else None

    def collect_snapshot(self, label: str) -> dict:
        snapshot_dir = self.output_dir / "snapshots" / label
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        commands = self._kubectl_commands()
        command_results = [
            self._run_snapshot_command(snapshot_dir, name, command)
            for name, command in commands
        ]

        prometheus_result = self._collect_prometheus(snapshot_dir)
        metadata = {
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "namespace": self.namespace,
            "commands": [asdict(result) for result in command_results],
            "prometheus": prometheus_result,
        }
        (snapshot_dir / "snapshot.json").write_text(json.dumps(metadata, indent=2))
        return metadata

    def collect_timeseries(
        self,
        label: str,
        start: datetime,
        end: datetime,
        rate_interval: str = "1m",
        step_seconds: int = 15,
    ) -> dict:
        timeseries_dir = self.output_dir / "timeseries" / label
        timeseries_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "namespace": self.namespace,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rate_interval": rate_interval,
            "step_seconds": step_seconds,
            "prometheus": self._collect_prometheus_range(
                timeseries_dir,
                start=start,
                end=end,
                rate_interval=rate_interval,
                step_seconds=step_seconds,
            ),
        }
        (timeseries_dir / "timeseries.json").write_text(json.dumps(metadata, indent=2))
        return metadata

    def collect_metrics(
        self,
        start: datetime,
        end: datetime,
        rate_window: str = "1m",
        step_seconds: int = 15,
    ) -> dict:
        metrics_dir = self.output_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "namespace": self.namespace,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rate_window": rate_window,
            "step_seconds": step_seconds,
            "prometheus": self._collect_named_prometheus_range(
                metrics_dir,
                start=start,
                end=end,
                rate_window=rate_window,
                step_seconds=step_seconds,
            ),
        }
        (metrics_dir / "metrics.json").write_text(json.dumps(metadata, indent=2))
        return metadata

    def _kubectl_commands(self) -> list[tuple[str, list[str]]]:
        ns = self.namespace
        return [
            ("pods-wide", ["kubectl", "get", "pods", "-n", ns, "-o", "wide"]),
            ("pods-json", ["kubectl", "get", "pods", "-n", ns, "-o", "json"]),
            (
                "deployments",
                ["kubectl", "get", "deployments", "-n", ns, "-o", "wide"],
            ),
            ("deployments-json", ["kubectl", "get", "deployments", "-n", ns, "-o", "json"]),
            ("hpa", ["kubectl", "get", "hpa", "-n", ns, "-o", "wide"]),
            ("services", ["kubectl", "get", "services", "-n", ns, "-o", "wide"]),
            (
                "events",
                ["kubectl", "get", "events", "-n", ns, "--sort-by=.lastTimestamp"],
            ),
            ("nodes", ["kubectl", "get", "nodes", "-o", "wide"]),
            ("top-pods", ["kubectl", "top", "pods", "-n", ns]),
            ("top-nodes", ["kubectl", "top", "nodes"]),
            (
                "pod-restarts",
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-n",
                    ns,
                    "-o",
                    "custom-columns=POD:.metadata.name,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount",
                ],
            ),
            (
                "resource-requests-limits",
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-n",
                    ns,
                    "-o",
                    "custom-columns=POD:.metadata.name,CONTAINER:.spec.containers[*].name,CPU_REQ:.spec.containers[*].resources.requests.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory,CPU_LIMIT:.spec.containers[*].resources.limits.cpu,MEM_LIMIT:.spec.containers[*].resources.limits.memory",
                ],
            ),
        ]

    def _prometheus_queries(self) -> dict[str, str]:
        ns = self.namespace
        return {
            "up": "up",
            "container_cpu_usage_rate": (
                f"sum(rate(container_cpu_usage_seconds_total{{namespace='{ns}'}}[5m])) "
                "by (pod)"
            ),
            "container_memory_working_set": (
                f"sum(container_memory_working_set_bytes{{namespace='{ns}'}}) by (pod)"
            ),
            "pod_restart_count": (
                f"sum(kube_pod_container_status_restarts_total{{namespace='{ns}'}}) "
                "by (pod)"
            ),
        }

    def _prometheus_range_queries(self, rate_interval: str) -> dict[str, str]:
        return self._render_metric_queries(rate_interval)

    def _run_snapshot_command(
        self, snapshot_dir: Path, name: str, command: list[str]
    ) -> SnapshotCommand:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

        stdout_file = f"{name}.out"
        stderr_file = f"{name}.err"
        (snapshot_dir / stdout_file).write_text(completed.stdout)
        (snapshot_dir / stderr_file).write_text(completed.stderr)

        return SnapshotCommand(
            name=name,
            command=command,
            returncode=completed.returncode,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
        )

    def _collect_prometheus(self, snapshot_dir: Path) -> dict:
        if not self.prometheus_url:
            return {"enabled": False, "reason": "no prometheus url supplied"}

        prometheus_dir = snapshot_dir / "prometheus"
        prometheus_dir.mkdir(parents=True, exist_ok=True)

        results = {"enabled": True, "queries": []}
        for name, query in self._prometheus_queries().items():
            query_url = (
                f"{self.prometheus_url}/api/v1/query?"
                + urllib.parse.urlencode({"query": query})
            )
            query_result = {
                "name": name,
                "query": query,
                "url": query_url,
                "ok": False,
                "output_file": f"{name}.json",
            }
            try:
                with urllib.request.urlopen(query_url, timeout=15) as response:
                    body = response.read().decode("utf-8")
                query_result["ok"] = True
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, indent=2)
                query_result["error"] = str(exc)

            (prometheus_dir / query_result["output_file"]).write_text(body)
            results["queries"].append(query_result)

        return results

    def _collect_prometheus_range(
        self,
        timeseries_dir: Path,
        start: datetime,
        end: datetime,
        rate_interval: str,
        step_seconds: int,
    ) -> dict:
        if not self.prometheus_url:
            return {"enabled": False, "reason": "no prometheus url supplied"}

        prometheus_dir = timeseries_dir / "prometheus"
        prometheus_dir.mkdir(parents=True, exist_ok=True)

        if end <= start:
            end = start

        results = {"enabled": True, "queries": []}
        for name, query in self._prometheus_range_queries(rate_interval).items():
            query_url = (
                f"{self.prometheus_url}/api/v1/query_range?"
                + urllib.parse.urlencode(
                    {
                        "query": query,
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "step": f"{step_seconds}s",
                    }
                )
            )
            output_file = f"{self._safe_filename(name)}.json"
            query_result = {
                "name": name,
                "query": query,
                "url": query_url,
                "ok": False,
                "output_file": output_file,
            }
            try:
                with urllib.request.urlopen(query_url, timeout=30) as response:
                    body = response.read().decode("utf-8")
                query_result["ok"] = True
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, indent=2)
                query_result["error"] = str(exc)

            (prometheus_dir / output_file).write_text(body)
            results["queries"].append(query_result)

        return results

    def _collect_named_prometheus_range(
        self,
        output_dir: Path,
        start: datetime,
        end: datetime,
        rate_window: str,
        step_seconds: int,
    ) -> dict:
        if not self.prometheus_url:
            return {"enabled": False, "reason": "no prometheus url supplied"}

        if end <= start:
            end = start

        results = {"enabled": True, "queries": []}
        for name, query in self._render_metric_queries(rate_window).items():
            query_url = self._query_range_url(
                query=query,
                start=start,
                end=end,
                step_seconds=step_seconds,
            )
            output_file = f"{name}.json"
            query_result = {
                "name": name,
                "query": query,
                "url": query_url,
                "ok": False,
                "output_file": output_file,
            }
            try:
                with urllib.request.urlopen(query_url, timeout=30) as response:
                    body = response.read().decode("utf-8")
                query_result["ok"] = True
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, indent=2)
                query_result["error"] = str(exc)

            (output_dir / output_file).write_text(body)
            results["queries"].append(query_result)

        return results

    def _render_metric_queries(self, rate_window: str) -> dict[str, str]:
        params = DEFAULT_QUERY_PARAMS | {
            "namespace": self.namespace,
            "rate_window": rate_window,
        }
        return {
            name: template.format(**params)
            for name, template in PROMETHEUS_QUERIES.items()
        }

    def _query_range_url(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> str:
        return (
            f"{self.prometheus_url}/api/v1/query_range?"
            + urllib.parse.urlencode(
                {
                    "query": query,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "step": f"{step_seconds}s",
                }
            )
        )

    def _safe_filename(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
