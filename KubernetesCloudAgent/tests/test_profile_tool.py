import json
import sys
import types
from datetime import datetime, timezone
from unittest import TestCase

if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")
    ansible_runner.run = lambda *_, **__: None
    sys.modules["ansible_runner"] = ansible_runner

from tools.profile import ClusterProfileTool


class FakeKubectl:
    def __init__(self, fail_resource: str | None = None) -> None:
        self.fail_resource = fail_resource
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> dict:
        self.calls.append(args)
        resource = args[1]
        if resource == self.fail_resource:
            return {"ok": False, "stderr": f"failed to get {resource}"}
        if resource == "pods" and "-A" in args:
            return {
                "ok": True,
                "stdout": (
                    "online-boutique frontend-abc-123 worker-node-1 "
                    "Running ReplicaSet frontend-abc"
                ),
                "stderr": "",
            }
        return {
            "ok": True,
            "stdout": json.dumps({"items": self._items(args)}),
            "stderr": "",
        }

    def _items(self, args: list[str]) -> list[dict]:
        resource = args[1]
        if resource == "deployments":
            return [
                {
                    "metadata": {"name": "frontend"},
                    "spec": {
                        "replicas": 1,
                        "template": {"metadata": {"labels": {"app": "frontend"}}},
                    },
                    "status": {
                        "availableReplicas": 1,
                        "conditions": [
                            {
                                "type": "Available",
                                "status": "True",
                                "reason": "MinimumReplicasAvailable",
                            }
                        ],
                    },
                }
            ]
        if resource == "replicasets":
            return [
                {
                    "metadata": {
                        "name": "frontend-abc",
                        "ownerReferences": [{"kind": "Deployment", "name": "frontend"}],
                    }
                }
            ]
        if resource == "pods":
            namespace = "online-boutique"
            pod = {
                "metadata": {
                    "name": "frontend-abc-123",
                    "namespace": namespace,
                    "ownerReferences": [{"kind": "ReplicaSet", "name": "frontend-abc"}],
                },
                "spec": {"nodeName": "worker-node-1"},
                "status": {
                    "phase": "Running",
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "containerStatuses": [
                        {"name": "server", "ready": True, "restartCount": 1}
                    ],
                },
            }
            return [pod]
        if resource == "services":
            return [
                {
                    "metadata": {"name": "frontend"},
                    "spec": {
                        "type": "ClusterIP",
                        "selector": {"app": "frontend"},
                        "ports": [
                            {
                                "name": "http",
                                "port": 80,
                                "targetPort": 8080,
                            }
                        ],
                    },
                }
            ]
        if resource == "endpoints":
            return [
                {
                    "metadata": {"name": "frontend"},
                    "subsets": [{"addresses": [{"ip": "192.0.2.25"}]}],
                }
            ]
        if resource == "horizontalpodautoscalers":
            return [
                {
                    "metadata": {"name": "frontend"},
                    "spec": {
                        "scaleTargetRef": {
                            "kind": "Deployment",
                            "name": "frontend",
                        },
                        "minReplicas": 1,
                        "maxReplicas": 5,
                    },
                    "status": {"currentReplicas": 1, "desiredReplicas": 1},
                }
            ]
        if resource == "nodes":
            return [
                {
                    "metadata": {
                        "name": "worker-node-1",
                        "labels": {
                            "role": "services",
                            "node-role.kubernetes.io/worker": "true",
                        },
                    },
                    "spec": {"unschedulable": False},
                    "status": {
                        "conditions": [
                            {"type": "Ready", "status": "True"},
                            {"type": "MemoryPressure", "status": "False"},
                            {"type": "DiskPressure", "status": "False"},
                            {"type": "PIDPressure", "status": "False"},
                        ],
                        "capacity": {"cpu": "4", "memory": "8Gi"},
                        "allocatable": {"cpu": "3900m", "memory": "7Gi"},
                    },
                }
            ]
        return []


class FakePrometheus:
    def __init__(self, fail_contains: str | None = None) -> None:
        self.fail_contains = fail_contains
        self.calls: list[dict] = []

    def query(self, promql: str, **kwargs) -> dict:
        self.calls.append({"promql": promql, **kwargs})
        if self.fail_contains and self.fail_contains in promql:
            return {"ok": False, "error": "Prometheus timeout"}
        label, value = self._value(promql)
        result = []
        if label:
            result = [
                {
                    "metric": {label[0]: label[1]},
                    "value": [0, str(value)],
                }
            ]
        return {
            "ok": True,
            "data": {
                "status": "success",
                "data": {"resultType": "vector", "result": result},
            },
        }

    def _value(self, promql: str):
        if 'reporter="source"' in promql:
            return None, None
        if "istio_request_duration_milliseconds_bucket" in promql:
            return ("destination_workload", "frontend"), 250
        if "response_code" in promql:
            return ("destination_workload", "frontend"), 1.5
        if "istio_requests_total" in promql:
            return ("destination_workload", "frontend"), 12.5
        if "istio_request_bytes_sum" in promql:
            return ("destination_workload", "frontend"), 4096
        if "container_cpu_usage_seconds_total" in promql:
            return ("pod", "frontend-abc-123"), 0.5
        if "container_memory_working_set_bytes" in promql:
            return ("pod", "frontend-abc-123"), 100
        if (
            "kube_pod_container_resource_limits" in promql
            and 'resource="cpu"' in promql
        ):
            return ("pod", "frontend-abc-123"), 2
        if (
            "kube_pod_container_resource_limits" in promql
            and 'resource="memory"' in promql
        ):
            return ("pod", "frontend-abc-123"), 400
        if 'resource="cpu"' in promql:
            return ("pod", "frontend-abc-123"), 1
        if 'resource="memory"' in promql:
            return ("pod", "frontend-abc-123"), 200
        if "container_fs_reads_bytes_total" in promql:
            return ("pod", "frontend-abc-123"), 5
        node_values = {
            "node_cpu_seconds_total": 20,
            "node_memory_MemAvailable_bytes": 40,
            "node_disk_read_bytes_total": 1000,
            "node_network_receive_bytes_total": 2000,
            "node_network_transmit_bytes_total": 3000,
            "node_network_receive_drop_total": 0.1,
            "node_network_receive_errs_total": 0.2,
            "node_netstat_Tcp_RetransSegs": 0.3,
        }
        for metric, value in node_values.items():
            if metric in promql:
                return ("node", "worker-node-1"), value
        return None, None


class FakeLoki:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def query(self, logql: str, **kwargs) -> dict:
        self.calls.append({"logql": logql, **kwargs})
        if self.fail:
            return {"ok": False, "error": "Loki unavailable"}
        return {
            "ok": True,
            "data": {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {
                                "namespace": "online-boutique",
                                "pod": "frontend-abc-123",
                            },
                            "values": [["123456789", "request timeout"]],
                        }
                    ],
                },
            },
        }


class FakeNetwork:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.latency_calls: list[dict] = []

    def topology(self, plane: str = "both") -> dict:
        if not self.ok:
            return {"ok": False, "error": "probe inventory unavailable"}
        return {
            "ok": True,
            "partial": False,
            "nodes": [
                {
                    "name": "worker-node-1",
                    "probes": {
                        "overlay": {"status": "ready", "count": 1},
                        "underlay": {"status": "ready", "count": 1},
                    },
                }
            ],
        }

    def latency_matrix(self, **kwargs) -> dict:
        self.latency_calls.append(kwargs)
        if not self.ok:
            return {
                "ok": False,
                "partial": False,
                "action": "latency_matrix",
                "error": "latency probes unavailable",
                "results": [],
            }
        return {
            "ok": True,
            "partial": False,
            "action": "latency_matrix",
            "planes": ["overlay", "underlay"],
            "count": kwargs["count"],
            "include_self": False,
            "pair_count": 0,
            "successful_pairs": 0,
            "failed_pairs": 0,
            "errors": [],
            "results": [],
        }


class ClusterProfileToolTest(TestCase):
    def _tool(
        self,
        *,
        kubectl: FakeKubectl | None = None,
        prometheus: FakePrometheus | None = None,
        loki: FakeLoki | None = None,
        network: FakeNetwork | None = None,
    ) -> ClusterProfileTool:
        return ClusterProfileTool(
            kubectl=kubectl or FakeKubectl(),
            prometheus=prometheus or FakePrometheus(),
            loki=loki or FakeLoki(),
            network=network or FakeNetwork(),
        )

    def test_profiles_all_discovered_services_and_nodes(self):
        kubectl = FakeKubectl()
        prometheus = FakePrometheus()
        network = FakeNetwork()
        result = self._tool(
            kubectl=kubectl,
            prometheus=prometheus,
            network=network,
        ).profile_baseline()

        self.assertTrue(result["ok"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["coverage"]["services_discovered"], 1)
        self.assertEqual(result["coverage"]["nodes_discovered"], 1)
        service = result["services"][0]
        self.assertEqual(service["name"], "frontend")
        self.assertEqual(service["kubernetes_health"], "ready")
        self.assertEqual(service["restart_count"], 1)
        self.assertEqual(
            service["placement"],
            [{"node": "worker-node-1", "pod_count": 1}],
        )
        self.assertEqual(service["services"][0]["ready_endpoints"], 1)
        self.assertEqual(service["metrics"]["traffic_rps"], 12.5)
        self.assertEqual(
            service["metrics"]["response_time_p95_seconds"],
            0.25,
        )
        self.assertEqual(
            service["metrics"]["cpu_request_utilization_percent"],
            50.0,
        )
        self.assertEqual(
            service["metrics"]["cpu_limit_utilization_percent"],
            25.0,
        )
        self.assertEqual(service["metric_scope"]["traffic"], "destination")
        node = result["nodes"][0]
        self.assertEqual(node["kubernetes_health"], "ready")
        self.assertEqual(node["workload_count"], 1)
        self.assertEqual(node["application_workloads"], ["frontend"])
        self.assertEqual(node["metrics"]["cpu_utilization_percent"], 20.0)
        self.assertEqual(node["probe_coverage"]["overlay"]["status"], "ready")
        self.assertEqual(result["latency_matrix"]["planes"], ["overlay", "underlay"])
        self.assertEqual(
            network.latency_calls,
            [{"plane": "both", "count": 10, "include_self": False}],
        )
        self.assertNotIn("warning_events", node)
        self.assertEqual(len(result["error_samples"]), 1)

        for args in kubectl.calls:
            self.assertIsInstance(args, list)
            self.assertFalse({"|", "&&", "||", ";", ">", "<"} & set(args))
            self.assertNotEqual(args[1], "events")
        self.assertEqual(len(prometheus.calls), 23)
        self.assertTrue(
            all(call["query_type"] == "instant" for call in prometheus.calls)
        )

    def test_preserves_partial_results_and_exact_failed_query(self):
        prometheus = FakePrometheus(fail_contains="node_disk_read_bytes_total")
        result = self._tool(
            prometheus=prometheus,
            loki=FakeLoki(fail=True),
            network=FakeNetwork(ok=False),
        ).profile_baseline()

        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(len(result["services"]), 1)
        self.assertEqual(len(result["nodes"]), 1)
        failed = next(
            error for error in result["errors"] if error["signal"] == "node_disk"
        )
        self.assertIn("node_disk_read_bytes_total", failed["query"])
        self.assertIn(
            "node/worker-node-1/disk_io_bytes_per_second",
            result["coverage"]["missing_signals"],
        )
        self.assertIn(
            "node/worker-node-1/probe_coverage",
            result["coverage"]["missing_signals"],
        )
        self.assertIn(
            "network/node_to_node_latency",
            result["coverage"]["missing_signals"],
        )
        self.assertFalse(result["latency_matrix"]["ok"])
        self.assertIn(
            "logs/error_samples",
            result["coverage"]["missing_signals"],
        )

    def test_reports_inventory_failure_without_dropping_other_profiles(self):
        result = self._tool(
            kubectl=FakeKubectl(fail_resource="horizontalpodautoscalers")
        ).profile_baseline()

        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["services"][0]["hpa"], None)
        self.assertIn(
            "kubernetes/hpas",
            result["coverage"]["missing_signals"],
        )
        failed = next(error for error in result["errors"] if error["signal"] == "hpas")
        self.assertEqual(
            failed["command"],
            [
                "kubectl",
                "get",
                "horizontalpodautoscalers",
                "-n",
                "online-boutique",
                "-o",
                "json",
            ],
        )

    def test_centers_window_on_detector_timestamp(self):
        result = self._tool().profile_baseline(
            evaluation_time=datetime(
                2026,
                7,
                30,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            include_error_samples=False,
        )

        self.assertEqual(result["window"]["mode"], "centered")
        self.assertEqual(result["window"]["start"], "2026-07-30T11:45:00Z")
        self.assertEqual(result["window"]["end"], "2026-07-30T12:15:00Z")
        self.assertEqual(result["error_samples"], [])
        self.assertNotIn(
            "logs/error_samples",
            result["coverage"]["missing_signals"],
        )

    def test_rejects_invalid_namespace_window_and_naive_timestamp(self):
        tool = self._tool()

        self.assertFalse(tool.profile_baseline(namespace="bad;namespace")["ok"])
        self.assertFalse(tool.profile_baseline(window_minutes=61)["ok"])
        self.assertFalse(
            tool.profile_baseline(evaluation_time="2026-07-31T12:00:00")["ok"]
        )
