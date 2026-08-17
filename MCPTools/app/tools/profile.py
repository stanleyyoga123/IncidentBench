import json
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any


class ClusterProfileTool:
    _NAMESPACE_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
    _MAX_ERROR_SAMPLES = 20
    _MAX_ERROR_LENGTH = 500

    def __init__(
        self,
        kubectl: Any,
        prometheus: Any,
        loki: Any,
        network: Any,
    ) -> None:
        self.kubectl = kubectl
        self.prometheus = prometheus
        self.loki = loki
        self.network = network

    def profile_baseline(
        self,
        namespace: str = "online-boutique",
        window_minutes: int = 30,
        evaluation_time: datetime | str | None = None,
        include_error_samples: bool = True,
    ) -> dict[str, Any]:
        validation_error = self._validate_request(
            namespace,
            window_minutes,
            evaluation_time,
        )
        if validation_error:
            return {
                "ok": False,
                "partial": False,
                "action": "profile_baseline",
                "error": validation_error,
            }

        observed_at = datetime.now(timezone.utc)
        evaluation = self._parse_datetime(evaluation_time)
        if evaluation and evaluation > observed_at + timedelta(minutes=5):
            return {
                "ok": False,
                "partial": False,
                "action": "profile_baseline",
                "error": "evaluation_time cannot be more than 5 minutes in the future",
            }
        window = self._profile_window(observed_at, evaluation, window_minutes)

        errors: list[dict[str, Any]] = []
        missing_signals: list[str] = []
        inventory = self._collect_inventory(namespace, errors, missing_signals)
        metrics = self._collect_metrics(
            namespace,
            window_minutes,
            window["end"],
            errors,
        )
        topology = self._collect_topology(errors)
        latency_matrix = self._collect_latency_matrix(
            errors,
            missing_signals,
        )
        error_samples = self._collect_error_samples(
            namespace,
            window["start"],
            window["end"],
            include_error_samples,
            errors,
        )

        services = self._build_service_profiles(
            namespace,
            inventory,
            metrics,
            missing_signals,
        )
        nodes = self._build_node_profiles(
            namespace,
            inventory,
            metrics,
            topology,
            missing_signals,
        )

        if include_error_samples and not error_samples:
            missing_signals.append("logs/error_samples")

        core_inventory = ("deployments", "pods", "nodes")
        missing_core = [name for name in core_inventory if inventory.get(name) is None]
        has_profiles = bool(services or nodes)
        partial = bool(errors or missing_signals or missing_core)
        return {
            "ok": not partial,
            "partial": partial and has_profiles,
            "action": "profile_baseline",
            "namespace": namespace,
            "observed_at": self._isoformat(observed_at),
            "window": {
                "mode": "centered" if evaluation else "recent",
                "minutes": window_minutes,
                "start": self._isoformat(window["start"]),
                "end": self._isoformat(window["end"]),
                "evaluation_time": (
                    self._isoformat(evaluation) if evaluation else None
                ),
            },
            "coverage": {
                "services_discovered": len(inventory.get("deployments") or []),
                "services_profiled": len(services),
                "nodes_discovered": len(inventory.get("nodes") or []),
                "nodes_profiled": len(nodes),
                "missing_signals": sorted(set(missing_signals)),
            },
            "services": services,
            "nodes": nodes,
            "latency_matrix": latency_matrix,
            "error_samples": error_samples,
            "errors": sorted(
                errors,
                key=lambda item: (
                    str(item.get("source", "")),
                    str(item.get("signal", "")),
                ),
            ),
        }

    def _validate_request(
        self,
        namespace: str,
        window_minutes: int,
        evaluation_time: datetime | str | None,
    ) -> str | None:
        if len(namespace) > 63 or not self._NAMESPACE_PATTERN.fullmatch(namespace):
            return "namespace must be a valid Kubernetes DNS label"
        if window_minutes < 5 or window_minutes > 60:
            return "window_minutes must be between 5 and 60"
        if (
            evaluation_time is not None
            and self._parse_datetime(evaluation_time) is None
        ):
            return "evaluation_time must be an ISO 8601 timestamp with a timezone"
        return None

    def _parse_datetime(
        self,
        value: datetime | str | None,
    ) -> datetime | None:
        if value is None:
            return None
        try:
            parsed = value
            if isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if not isinstance(parsed, datetime) or parsed.tzinfo is None:
                return None
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    def _profile_window(
        self,
        observed_at: datetime,
        evaluation: datetime | None,
        window_minutes: int,
    ) -> dict[str, datetime]:
        if not evaluation:
            return {
                "start": observed_at - timedelta(minutes=window_minutes),
                "end": observed_at,
            }
        half_window = timedelta(minutes=window_minutes / 2)
        return {
            "start": evaluation - half_window,
            "end": min(evaluation + half_window, observed_at),
        }

    def _collect_inventory(
        self,
        namespace: str,
        errors: list[dict[str, Any]],
        missing_signals: list[str],
    ) -> dict[str, list[dict[str, Any]] | None]:
        commands = {
            "deployments": [
                "get",
                "deployments",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            "replicasets": [
                "get",
                "replicasets",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            "pods": ["get", "pods", "-n", namespace, "-o", "json"],
            "services": [
                "get",
                "services",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            "endpoints": [
                "get",
                "endpoints",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            "hpas": [
                "get",
                "horizontalpodautoscalers",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            "nodes": ["get", "nodes", "-o", "json"],
        }
        inventory: dict[str, list[dict[str, Any]] | None] = {}
        for name, args in commands.items():
            result = self._kubectl_items(args)
            if result.get("ok"):
                inventory[name] = result["items"]
                continue
            inventory[name] = None
            missing_signals.append(f"kubernetes/{name}")
            errors.append(
                {
                    "source": "kubectl",
                    "signal": name,
                    "command": ["kubectl", *args],
                    "error": result.get("error", "inventory command failed"),
                }
            )
        pod_args = [
            "get",
            "pods",
            "-A",
            "-o",
            "custom-columns=NAMESPACE:.metadata.namespace,"
            "NAME:.metadata.name,"
            "NODE:.spec.nodeName,"
            "PHASE:.status.phase,"
            "OWNER_KIND:.metadata.ownerReferences[0].kind,"
            "OWNER_NAME:.metadata.ownerReferences[0].name",
            "--no-headers",
        ]
        pod_result = self._kubectl_pod_rows(pod_args)
        if pod_result.get("ok"):
            inventory["all_pods"] = pod_result["items"]
        else:
            inventory["all_pods"] = None
            missing_signals.append("kubernetes/all_pods")
            errors.append(
                {
                    "source": "kubectl",
                    "signal": "all_pods",
                    "command": ["kubectl", *pod_args],
                    "error": pod_result.get(
                        "error",
                        "workload inventory command failed",
                    ),
                }
            )
        return inventory

    def _kubectl_items(self, args: list[str]) -> dict[str, Any]:
        try:
            result = self.kubectl.run(args)
        except Exception as exc:
            return {"ok": False, "error": self._bounded_error(exc)}
        if not result.get("ok"):
            return {
                "ok": False,
                "error": self._command_error(result),
            }
        try:
            data = json.loads(result.get("stdout", ""))
        except (TypeError, json.JSONDecodeError):
            return {"ok": False, "error": "kubectl returned malformed JSON"}
        items = data.get("items")
        if not isinstance(items, list):
            return {"ok": False, "error": "kubectl JSON did not contain an items list"}
        return {"ok": True, "items": items}

    def _kubectl_pod_rows(self, args: list[str]) -> dict[str, Any]:
        try:
            result = self.kubectl.run(args)
        except Exception as exc:
            return {"ok": False, "error": self._bounded_error(exc)}
        if not result.get("ok"):
            return {"ok": False, "error": self._command_error(result)}

        items = []
        for line in str(result.get("stdout", "")).splitlines():
            fields = line.split()
            if len(fields) != 6:
                return {
                    "ok": False,
                    "error": "kubectl returned malformed workload inventory",
                }
            namespace, name, node, phase, owner_kind, owner_name = fields
            owner_references = []
            if owner_kind != "<none>" and owner_name != "<none>":
                owner_references.append({"kind": owner_kind, "name": owner_name})
            items.append(
                {
                    "metadata": {
                        "namespace": namespace,
                        "name": name,
                        "ownerReferences": owner_references,
                    },
                    "spec": {
                        "nodeName": None if node == "<none>" else node,
                    },
                    "status": {"phase": phase},
                }
            )
        return {"ok": True, "items": items}

    def _collect_metrics(
        self,
        namespace: str,
        window_minutes: int,
        query_time: datetime,
        errors: list[dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        rate_window = f"{window_minutes}m"
        selector = f'namespace="{namespace}"'
        destination = (
            'reporter="destination",'
            f'destination_workload_namespace="{namespace}",'
            'destination_workload!="unknown"'
        )
        source = (
            'reporter="source",'
            f'source_workload_namespace="{namespace}",'
            'source_workload!="unknown"'
        )
        queries = {
            "traffic_destination": (
                "destination_workload",
                "sum by (destination_workload) "
                f"(rate(istio_requests_total{{{destination}}}[{rate_window}]))",
            ),
            "traffic_source": (
                "source_workload",
                "sum by (source_workload) "
                f"(rate(istio_requests_total{{{source}}}[{rate_window}]))",
            ),
            "p95_destination": (
                "destination_workload",
                "histogram_quantile(0.95, "
                "sum by (destination_workload, le) "
                f"(rate(istio_request_duration_milliseconds_bucket{{{destination}}}"
                f"[{rate_window}])))",
            ),
            "p95_source": (
                "source_workload",
                "histogram_quantile(0.95, "
                "sum by (source_workload, le) "
                f"(rate(istio_request_duration_milliseconds_bucket{{{source}}}"
                f"[{rate_window}])))",
            ),
            "errors_destination": (
                "destination_workload",
                "100 * (sum by (destination_workload) "
                f'(rate(istio_requests_total{{{destination},response_code=~"5.."}}'
                f"[{rate_window}])) or 0 * sum by (destination_workload) "
                f"(rate(istio_requests_total{{{destination}}}[{rate_window}]))) "
                "/ sum by (destination_workload) "
                f"(rate(istio_requests_total{{{destination}}}[{rate_window}]))",
            ),
            "errors_source": (
                "source_workload",
                "100 * (sum by (source_workload) "
                f'(rate(istio_requests_total{{{source},response_code=~"5.."}}'
                f"[{rate_window}])) or 0 * sum by (source_workload) "
                f"(rate(istio_requests_total{{{source}}}[{rate_window}]))) "
                "/ sum by (source_workload) "
                f"(rate(istio_requests_total{{{source}}}[{rate_window}]))",
            ),
            "network_destination": (
                "destination_workload",
                "sum by (destination_workload) "
                f"(rate(istio_request_bytes_sum{{{destination}}}[{rate_window}]) + "
                f"rate(istio_response_bytes_sum{{{destination}}}[{rate_window}]))",
            ),
            "network_source": (
                "source_workload",
                "sum by (source_workload) "
                f"(rate(istio_request_bytes_sum{{{source}}}[{rate_window}]) + "
                f"rate(istio_response_bytes_sum{{{source}}}[{rate_window}]))",
            ),
            "pod_cpu": (
                "pod",
                "sum by (pod) "
                f"(rate(container_cpu_usage_seconds_total{{{selector},"
                f'container!="",container!="POD"}}[{rate_window}]))',
            ),
            "pod_memory": (
                "pod",
                "sum by (pod) "
                f'(container_memory_working_set_bytes{{{selector},container!="",'
                'container!="POD"})',
            ),
            "pod_cpu_requests": (
                "pod",
                "sum by (pod) "
                f'(kube_pod_container_resource_requests{{{selector},resource="cpu",'
                'unit="core"})',
            ),
            "pod_memory_requests": (
                "pod",
                "sum by (pod) "
                f"(kube_pod_container_resource_requests{{{selector},"
                'resource="memory",unit="byte"})',
            ),
            "pod_cpu_limits": (
                "pod",
                "sum by (pod) "
                f'(kube_pod_container_resource_limits{{{selector},resource="cpu",'
                'unit="core"})',
            ),
            "pod_memory_limits": (
                "pod",
                "sum by (pod) "
                f"(kube_pod_container_resource_limits{{{selector},"
                'resource="memory",unit="byte"})',
            ),
            "pod_disk": (
                "pod",
                "sum by (pod) "
                f"(rate(container_fs_reads_bytes_total{{{selector},"
                f'container!="",container!="POD"}}[{rate_window}]) + '
                f"rate(container_fs_writes_bytes_total{{{selector},"
                f'container!="",container!="POD"}}[{rate_window}]))',
            ),
            "node_cpu": (
                "node",
                "100 * (1 - avg by (node) "
                f'(rate(node_cpu_seconds_total{{mode="idle"}}[{rate_window}])))',
            ),
            "node_memory": (
                "node",
                "100 * (1 - node_memory_MemAvailable_bytes "
                "/ node_memory_MemTotal_bytes)",
            ),
            "node_disk": (
                "node",
                "sum by (node) "
                f"(rate(node_disk_read_bytes_total[{rate_window}]) + "
                f"rate(node_disk_written_bytes_total[{rate_window}]))",
            ),
            "node_rx": (
                "node",
                "sum by (node) "
                f'(rate(node_network_receive_bytes_total{{device!="lo"}}'
                f"[{rate_window}]))",
            ),
            "node_tx": (
                "node",
                "sum by (node) "
                f'(rate(node_network_transmit_bytes_total{{device!="lo"}}'
                f"[{rate_window}]))",
            ),
            "node_drops": (
                "node",
                "sum by (node) "
                f'(rate(node_network_receive_drop_total{{device!="lo"}}'
                f"[{rate_window}]) + "
                f'rate(node_network_transmit_drop_total{{device!="lo"}}'
                f"[{rate_window}]))",
            ),
            "node_errors": (
                "node",
                "sum by (node) "
                f'(rate(node_network_receive_errs_total{{device!="lo"}}'
                f"[{rate_window}]) + "
                f'rate(node_network_transmit_errs_total{{device!="lo"}}'
                f"[{rate_window}]))",
            ),
            "node_retransmits": (
                "node",
                "sum by (node) " f"(rate(node_netstat_Tcp_RetransSegs[{rate_window}]))",
            ),
        }

        collected: dict[str, dict[str, float]] = {}
        query_time_value = self._isoformat(query_time)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(
                    self._prometheus_vector,
                    promql,
                    label,
                    query_time_value,
                ): (name, promql)
                for name, (label, promql) in queries.items()
            }
            for future in as_completed(futures):
                name, promql = futures[future]
                try:
                    collected[name] = future.result()
                except Exception as exc:
                    collected[name] = {}
                    errors.append(
                        {
                            "source": "prometheus",
                            "signal": name,
                            "query": promql,
                            "error": self._bounded_error(exc),
                        }
                    )
        return collected

    def _prometheus_vector(
        self,
        promql: str,
        label: str,
        query_time: str,
    ) -> dict[str, float]:
        result = self.prometheus.query(
            promql,
            query_type="instant",
            time=query_time,
        )
        if not isinstance(result, dict):
            raise ValueError("Prometheus returned malformed data")
        if not result.get("ok"):
            raise ValueError(self._command_error(result))
        response = result.get("data")
        if not isinstance(response, dict) or response.get("status") != "success":
            raise ValueError("Prometheus returned an unsuccessful response")
        payload = response.get("data")
        if not isinstance(payload, dict) or not isinstance(
            payload.get("result"),
            list,
        ):
            raise ValueError("Prometheus returned malformed vector data")

        values: dict[str, float] = {}
        for item in payload["result"]:
            metric = item.get("metric") or {}
            name = metric.get(label)
            value = item.get("value")
            if not name or not isinstance(value, list) or len(value) < 2:
                continue
            parsed = self._finite_float(value[1])
            if parsed is not None:
                values[str(name)] = parsed
        return values

    def _collect_topology(
        self,
        errors: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            result = self.network.topology(plane="both")
        except Exception as exc:
            result = {"ok": False, "error": self._bounded_error(exc)}
        if not isinstance(result, dict):
            result = {"ok": False, "error": "network topology returned malformed data"}
        if not result.get("ok"):
            errors.append(
                {
                    "source": "network.topology",
                    "signal": "probe_coverage",
                    "error": self._command_error(result),
                }
            )
        if isinstance(result.get("nodes"), list):
            return result
        return None

    def _collect_latency_matrix(
        self,
        errors: list[dict[str, Any]],
        missing_signals: list[str],
    ) -> dict[str, Any]:
        try:
            result = self.network.latency_matrix(
                plane="both",
                count=10,
                include_self=False,
            )
        except Exception as exc:
            result = {
                "ok": False,
                "partial": False,
                "action": "latency_matrix",
                "error": self._bounded_error(exc),
            }
        if not isinstance(result, dict):
            result = {
                "ok": False,
                "partial": False,
                "action": "latency_matrix",
                "error": "network latency matrix returned malformed data",
            }
        if not result.get("ok"):
            missing_signals.append("network/node_to_node_latency")
            errors.append(
                {
                    "source": "network.latency_matrix",
                    "signal": "node_to_node_latency",
                    "error": self._latency_matrix_error(result),
                }
            )
        return result

    def _latency_matrix_error(self, result: dict[str, Any]) -> str:
        if result.get("error"):
            return self._command_error(result)
        details = list(result.get("errors") or [])
        details.extend(
            {
                "plane": item.get("plane"),
                "source_node": item.get("source_node"),
                "target_node": item.get("target_node"),
                "error": item.get("error"),
            }
            for item in result.get("results") or []
            if isinstance(item, dict) and not item.get("ok")
        )
        if not details:
            return "latency matrix failed without error details"
        return json.dumps(details, sort_keys=True)[: self._MAX_ERROR_LENGTH]

    def _collect_error_samples(
        self,
        namespace: str,
        start: datetime,
        end: datetime,
        enabled: bool,
        errors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not enabled:
            return []
        logql = (
            f'{{namespace="{namespace}"}} '
            '|~ "(?i)(error|exception|panic|timeout|connection refused|reset)"'
        )
        try:
            result = self.loki.query(
                logql,
                query_type="range",
                start=self._isoformat(start),
                end=self._isoformat(end),
                limit=self._MAX_ERROR_SAMPLES,
                direction="BACKWARD",
            )
        except Exception as exc:
            result = {"ok": False, "error": self._bounded_error(exc)}
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Loki returned malformed data"}
        if not result.get("ok"):
            errors.append(
                {
                    "source": "loki",
                    "signal": "error_samples",
                    "query": logql,
                    "error": self._command_error(result),
                }
            )
            return []
        response = result.get("data")
        payload = response.get("data") if isinstance(response, dict) else None
        streams = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(streams, list):
            errors.append(
                {
                    "source": "loki",
                    "signal": "error_samples",
                    "query": logql,
                    "error": "Loki returned malformed stream data",
                }
            )
            return []

        samples = []
        for item in streams:
            labels = item.get("stream") or {}
            for timestamp, line in item.get("values") or []:
                samples.append(
                    {
                        "timestamp": str(timestamp),
                        "labels": labels,
                        "line": str(line)[: self._MAX_ERROR_LENGTH],
                    }
                )
                if len(samples) >= self._MAX_ERROR_SAMPLES:
                    return samples
        return samples

    def _build_service_profiles(
        self,
        namespace: str,
        inventory: dict[str, list[dict[str, Any]] | None],
        metrics: dict[str, dict[str, float]],
        missing_signals: list[str],
    ) -> list[dict[str, Any]]:
        deployments = inventory.get("deployments") or []
        replicasets = inventory.get("replicasets") or []
        pods = inventory.get("pods") or []
        services = inventory.get("services") or []
        endpoints = inventory.get("endpoints") or []
        hpas = inventory.get("hpas") or []

        rs_owners = {
            item.get("metadata", {}).get("name"): self._owner_name(
                item,
                "Deployment",
            )
            for item in replicasets
        }
        pods_by_deployment: dict[str, list[dict[str, Any]]] = {}
        for pod in pods:
            replica_set = self._owner_name(pod, "ReplicaSet")
            deployment = rs_owners.get(replica_set)
            if deployment:
                pods_by_deployment.setdefault(deployment, []).append(pod)

        endpoint_by_name = {
            item.get("metadata", {}).get("name"): item for item in endpoints
        }
        hpa_by_target = {
            item.get("spec", {}).get("scaleTargetRef", {}).get("name"): item
            for item in hpas
            if item.get("spec", {}).get("scaleTargetRef", {}).get("kind")
            == "Deployment"
        }
        profiles = []
        for deployment in sorted(
            deployments,
            key=lambda item: item.get("metadata", {}).get("name", ""),
        ):
            name = deployment.get("metadata", {}).get("name", "")
            deployment_pods = pods_by_deployment.get(name, [])
            pod_names = [
                pod.get("metadata", {}).get("name", "") for pod in deployment_pods
            ]
            desired = deployment.get("spec", {}).get("replicas", 1)
            available = deployment.get("status", {}).get(
                "availableReplicas",
                0,
            )
            ready_pods = sum(self._pod_ready(pod) for pod in deployment_pods)
            pod_profiles = [
                self._pod_profile(pod)
                for pod in sorted(
                    deployment_pods,
                    key=lambda item: item.get("metadata", {}).get("name", ""),
                )
            ]
            placement = Counter(
                pod.get("spec", {}).get("nodeName") or "unscheduled"
                for pod in deployment_pods
            )

            template_labels = (
                deployment.get("spec", {})
                .get("template", {})
                .get("metadata", {})
                .get("labels", {})
            )
            service_profiles = []
            for service in services:
                service_selector = service.get("spec", {}).get("selector") or {}
                if not service_selector or not self._labels_match(
                    template_labels,
                    service_selector,
                ):
                    continue
                service_name = service.get("metadata", {}).get("name", "")
                endpoint = endpoint_by_name.get(service_name) or {}
                ready_endpoints = sum(
                    len(subset.get("addresses") or [])
                    for subset in endpoint.get("subsets") or []
                )
                not_ready_endpoints = sum(
                    len(subset.get("notReadyAddresses") or [])
                    for subset in endpoint.get("subsets") or []
                )
                service_profiles.append(
                    {
                        "name": service_name,
                        "type": service.get("spec", {}).get("type"),
                        "ports": [
                            {
                                "name": port.get("name"),
                                "port": port.get("port"),
                                "target_port": port.get("targetPort"),
                            }
                            for port in service.get("spec", {}).get("ports", [])
                        ],
                        "ready_endpoints": ready_endpoints,
                        "not_ready_endpoints": not_ready_endpoints,
                    }
                )

            profile_metrics, metric_scope = self._service_metrics(
                name,
                pod_names,
                metrics,
            )
            service_missing = [
                metric_name
                for metric_name, value in profile_metrics.items()
                if value is None
            ]
            missing_signals.extend(
                f"service/{name}/{signal}" for signal in service_missing
            )
            profiles.append(
                {
                    "name": name,
                    "namespace": namespace,
                    "kubernetes_health": (
                        "ready"
                        if desired > 0
                        and available >= desired
                        and ready_pods >= desired
                        else "degraded"
                    ),
                    "replicas": {
                        "desired": desired,
                        "available": available,
                        "ready_pods": ready_pods,
                    },
                    "restart_count": sum(pod["restart_count"] for pod in pod_profiles),
                    "placement": [
                        {"node": node, "pod_count": count}
                        for node, count in sorted(placement.items())
                    ],
                    "pods": pod_profiles,
                    "services": service_profiles,
                    "hpa": self._hpa_profile(hpa_by_target.get(name)),
                    "conditions": self._conditions(deployment),
                    "metrics": profile_metrics,
                    "metric_scope": metric_scope,
                    "missing_signals": service_missing,
                }
            )
        return profiles

    def _service_metrics(
        self,
        deployment: str,
        pod_names: list[str],
        metrics: dict[str, dict[str, float]],
    ) -> tuple[dict[str, float | None], dict[str, str | None]]:
        traffic, traffic_scope = self._preferred_workload_metric(
            metrics,
            deployment,
            "traffic_destination",
            "traffic_source",
        )
        p95, p95_scope = self._preferred_workload_metric(
            metrics,
            deployment,
            "p95_destination",
            "p95_source",
        )
        errors, errors_scope = self._preferred_workload_metric(
            metrics,
            deployment,
            "errors_destination",
            "errors_source",
        )
        network, network_scope = self._preferred_workload_metric(
            metrics,
            deployment,
            "network_destination",
            "network_source",
        )
        cpu = self._sum_values(metrics.get("pod_cpu", {}), pod_names)
        memory = self._sum_values(metrics.get("pod_memory", {}), pod_names)
        cpu_requests = self._sum_values(
            metrics.get("pod_cpu_requests", {}),
            pod_names,
        )
        memory_requests = self._sum_values(
            metrics.get("pod_memory_requests", {}),
            pod_names,
        )
        cpu_limits = self._sum_values(
            metrics.get("pod_cpu_limits", {}),
            pod_names,
        )
        memory_limits = self._sum_values(
            metrics.get("pod_memory_limits", {}),
            pod_names,
        )
        disk = self._sum_values(metrics.get("pod_disk", {}), pod_names)
        return (
            {
                "traffic_rps": self._rounded(traffic),
                "response_time_p95_seconds": self._rounded(
                    p95 / 1000 if p95 is not None else None,
                ),
                "http_5xx_rate_percent": self._rounded(errors),
                "cpu_usage_cores": self._rounded(cpu),
                "cpu_request_cores": self._rounded(cpu_requests),
                "cpu_request_utilization_percent": self._percent(
                    cpu,
                    cpu_requests,
                ),
                "cpu_limit_cores": self._rounded(cpu_limits),
                "cpu_limit_utilization_percent": self._percent(
                    cpu,
                    cpu_limits,
                ),
                "memory_working_set_bytes": self._rounded(memory),
                "memory_request_bytes": self._rounded(memory_requests),
                "memory_request_utilization_percent": self._percent(
                    memory,
                    memory_requests,
                ),
                "memory_limit_bytes": self._rounded(memory_limits),
                "memory_limit_utilization_percent": self._percent(
                    memory,
                    memory_limits,
                ),
                "network_io_bytes_per_second": self._rounded(network),
                "disk_io_bytes_per_second": self._rounded(disk),
            },
            {
                "traffic": traffic_scope,
                "latency": p95_scope,
                "errors": errors_scope,
                "network": network_scope,
            },
        )

    def _preferred_workload_metric(
        self,
        metrics: dict[str, dict[str, float]],
        workload: str,
        destination_name: str,
        source_name: str,
    ) -> tuple[float | None, str | None]:
        destination = metrics.get(destination_name, {})
        if workload in destination:
            return destination[workload], "destination"
        source = metrics.get(source_name, {})
        if workload in source:
            return source[workload], "source_fallback"
        return None, None

    def _build_node_profiles(
        self,
        namespace: str,
        inventory: dict[str, list[dict[str, Any]] | None],
        metrics: dict[str, dict[str, float]],
        topology: dict[str, Any] | None,
        missing_signals: list[str],
    ) -> list[dict[str, Any]]:
        nodes = inventory.get("nodes") or []
        all_pods = inventory.get("all_pods")
        replicasets = inventory.get("replicasets") or []
        replica_set_owners = {
            item.get("metadata", {}).get("name"): self._owner_name(
                item,
                "Deployment",
            )
            for item in replicasets
        }
        topology_nodes = {
            item.get("name"): item for item in (topology or {}).get("nodes", [])
        }
        profiles = []
        for node in sorted(
            nodes,
            key=lambda item: item.get("metadata", {}).get("name", ""),
        ):
            name = node.get("metadata", {}).get("name", "")
            labels = node.get("metadata", {}).get("labels", {})
            node_pods = [
                pod
                for pod in (all_pods or [])
                if pod.get("spec", {}).get("nodeName") == name
                and pod.get("status", {}).get("phase") not in {"Succeeded", "Failed"}
            ]
            namespace_counts = (
                Counter(
                    pod.get("metadata", {}).get("namespace", "default")
                    for pod in node_pods
                )
                if all_pods is not None
                else None
            )
            app_workloads = (
                sorted(
                    {
                        self._pod_workload_name(pod, replica_set_owners)
                        for pod in node_pods
                        if pod.get("metadata", {}).get("namespace") == namespace
                    }
                )
                if all_pods is not None
                else None
            )
            conditions = self._condition_map(node)
            ready = conditions.get("Ready", {}).get("status") == "True"
            schedulable = not node.get("spec", {}).get(
                "unschedulable",
                False,
            )
            pressures = {
                condition: conditions.get(condition, {}).get("status") == "True"
                for condition in (
                    "MemoryPressure",
                    "DiskPressure",
                    "PIDPressure",
                )
            }
            topology_node = topology_nodes.get(name)
            is_service_worker = labels.get("role") == "services"
            if topology_node:
                probe_coverage: dict[str, Any] | str = topology_node.get(
                    "probes",
                    {},
                )
            elif is_service_worker:
                probe_coverage = "missing"
            else:
                probe_coverage = "not_applicable"

            node_metrics = {
                "cpu_utilization_percent": self._metric_value(
                    metrics,
                    "node_cpu",
                    name,
                ),
                "memory_utilization_percent": self._metric_value(
                    metrics,
                    "node_memory",
                    name,
                ),
                "disk_io_bytes_per_second": self._metric_value(
                    metrics,
                    "node_disk",
                    name,
                ),
                "network_receive_bytes_per_second": self._metric_value(
                    metrics,
                    "node_rx",
                    name,
                ),
                "network_transmit_bytes_per_second": self._metric_value(
                    metrics,
                    "node_tx",
                    name,
                ),
                "network_drops_per_second": self._metric_value(
                    metrics,
                    "node_drops",
                    name,
                ),
                "network_errors_per_second": self._metric_value(
                    metrics,
                    "node_errors",
                    name,
                ),
                "tcp_retransmits_per_second": self._metric_value(
                    metrics,
                    "node_retransmits",
                    name,
                ),
            }
            node_missing = [
                metric_name
                for metric_name, value in node_metrics.items()
                if value is None
            ]
            if is_service_worker:
                if topology_node is None:
                    node_missing.append("probe_coverage")
                elif isinstance(probe_coverage, dict):
                    for plane in ("overlay", "underlay"):
                        if probe_coverage.get(plane, {}).get("status") != "ready":
                            node_missing.append(f"probe_coverage/{plane}")
            if all_pods is None:
                node_missing.append("workload_placement")
            missing_signals.extend(f"node/{name}/{signal}" for signal in node_missing)
            profiles.append(
                {
                    "name": name,
                    "kubernetes_health": (
                        "ready"
                        if ready and schedulable and not any(pressures.values())
                        else "degraded"
                    ),
                    "ready": ready,
                    "schedulable": schedulable,
                    "roles": sorted(
                        key.removeprefix("node-role.kubernetes.io/")
                        for key in labels
                        if key.startswith("node-role.kubernetes.io/")
                    ),
                    "role": labels.get("role"),
                    "pressure": pressures,
                    "capacity": node.get("status", {}).get("capacity", {}),
                    "allocatable": node.get("status", {}).get(
                        "allocatable",
                        {},
                    ),
                    "workload_count": (
                        len(node_pods) if all_pods is not None else None
                    ),
                    "workload_count_scope": "kubectl_inventory",
                    "workloads_by_namespace": (
                        dict(sorted(namespace_counts.items()))
                        if namespace_counts is not None
                        else None
                    ),
                    "application_workloads": app_workloads,
                    "probe_coverage": probe_coverage,
                    "metrics": node_metrics,
                    "missing_signals": node_missing,
                }
            )
        return profiles

    def _pod_profile(self, pod: dict[str, Any]) -> dict[str, Any]:
        statuses = pod.get("status", {}).get("containerStatuses") or []
        return {
            "name": pod.get("metadata", {}).get("name"),
            "node": pod.get("spec", {}).get("nodeName"),
            "phase": pod.get("status", {}).get("phase"),
            "ready": bool(self._pod_ready(pod)),
            "restart_count": sum(status.get("restartCount", 0) for status in statuses),
        }

    def _pod_ready(self, pod: dict[str, Any]) -> int:
        return int(
            any(
                condition.get("type") == "Ready" and condition.get("status") == "True"
                for condition in pod.get("status", {}).get("conditions", [])
            )
        )

    def _hpa_profile(
        self,
        hpa: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not hpa:
            return None
        return {
            "name": hpa.get("metadata", {}).get("name"),
            "min_replicas": hpa.get("spec", {}).get("minReplicas", 1),
            "max_replicas": hpa.get("spec", {}).get("maxReplicas"),
            "current_replicas": hpa.get("status", {}).get(
                "currentReplicas",
            ),
            "desired_replicas": hpa.get("status", {}).get(
                "desiredReplicas",
            ),
            "current_metrics": hpa.get("status", {}).get("currentMetrics", []),
            "conditions": self._conditions(hpa),
        }

    def _conditions(self, resource: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "type": condition.get("type"),
                "status": condition.get("status"),
                "reason": condition.get("reason"),
                "message": condition.get("message"),
            }
            for condition in resource.get("status", {}).get("conditions", [])
        ]

    def _condition_map(
        self,
        resource: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return {
            condition.get("type"): condition
            for condition in resource.get("status", {}).get("conditions", [])
        }

    def _owner_name(
        self,
        resource: dict[str, Any],
        kind: str,
    ) -> str | None:
        for owner in resource.get("metadata", {}).get("ownerReferences", []):
            if owner.get("kind") == kind:
                return owner.get("name")
        return None

    def _pod_workload_name(
        self,
        pod: dict[str, Any],
        replica_set_owners: dict[str | None, str | None],
    ) -> str:
        replica_set = self._owner_name(pod, "ReplicaSet")
        return (
            replica_set_owners.get(replica_set)
            or replica_set
            or self._owner_name(pod, "DaemonSet")
            or self._owner_name(pod, "StatefulSet")
            or pod.get("metadata", {}).get("name", "")
        )

    def _labels_match(
        self,
        resource_labels: dict[str, str],
        selector: dict[str, str],
    ) -> bool:
        return all(resource_labels.get(key) == value for key, value in selector.items())

    def _sum_values(
        self,
        values: dict[str, float],
        names: list[str],
    ) -> float | None:
        selected = [values[name] for name in names if name in values]
        return sum(selected) if selected else None

    def _metric_value(
        self,
        metrics: dict[str, dict[str, float]],
        metric_name: str,
        resource_name: str,
    ) -> float | None:
        return self._rounded(metrics.get(metric_name, {}).get(resource_name))

    def _percent(
        self,
        numerator: float | None,
        denominator: float | None,
    ) -> float | None:
        if numerator is None or denominator is None or denominator <= 0:
            return None
        return self._rounded(100 * numerator / denominator)

    def _finite_float(self, value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    def _rounded(self, value: float | None) -> float | None:
        return round(value, 6) if value is not None else None

    def _isoformat(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _command_error(self, result: dict[str, Any]) -> str:
        error = result.get("error")
        if error:
            return str(error)[: self._MAX_ERROR_LENGTH]
        stderr = str(result.get("stderr", "")).strip()
        if stderr:
            return stderr[: self._MAX_ERROR_LENGTH]
        return "tool call failed"

    def _bounded_error(self, exc: Exception) -> str:
        return str(exc)[: self._MAX_ERROR_LENGTH]
