import json
import sys
import types
from unittest import TestCase
from unittest.mock import patch

if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")
    ansible_runner.run = lambda *_, **__: None
    sys.modules["ansible_runner"] = ansible_runner

from tools.network import NetworkTool


class NetworkToolTest(TestCase):
    def setUp(self):
        self.tool = NetworkTool(
            path="kubectl",
            namespace="utility",
            timeout_seconds=30,
            max_duration_seconds=10,
            max_bitrate_mbps=100,
            max_matrix_nodes=6,
        )

    def test_topology_distinguishes_overlay_and_underlay_probes(self):
        with patch(
            "tools.network.run_command",
            side_effect=self._inventory_commands,
        ):
            result = self.tool.topology()

        self.assertTrue(result["ok"])
        self.assertEqual(result["worker_count"], 2)
        self.assertEqual(result["ready_probe_count"], 4)
        worker = next(
            item for item in result["nodes"] if item["name"] == "worker-node-1"
        )
        self.assertEqual(worker["internal_ip"], "192.0.2.3")
        self.assertEqual(worker["pod_cidr"], "192.0.2.22/24")
        self.assertEqual(worker["probes"]["overlay"]["status"], "ready")
        self.assertEqual(worker["probes"]["underlay"]["status"], "ready")

    def test_topology_reports_missing_probe_as_missing_evidence(self):
        def commands(args, timeout):
            result = self._inventory_commands(args, timeout)
            if self._is_pod_inventory(args, "underlay"):
                data = json.loads(result["stdout"])
                data["items"] = [
                    item
                    for item in data["items"]
                    if item["spec"]["nodeName"] != "worker-node-2"
                ]
                return self._success(data)
            return result

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.topology()

        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        worker = next(
            item for item in result["nodes"] if item["name"] == "worker-node-2"
        )
        self.assertEqual(worker["probes"]["underlay"]["status"], "missing")

    def test_topology_reports_duplicate_probe(self):
        def commands(args, timeout):
            result = self._inventory_commands(args, timeout)
            if self._is_pod_inventory(args, "overlay"):
                data = json.loads(result["stdout"])
                duplicate = self._pod(
                    "overlay-worker-node-1-duplicate",
                    "worker-node-1",
                    "192.0.2.23",
                )
                data["items"].append(duplicate)
                return self._success(data)
            return result

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.topology(plane="overlay")

        self.assertFalse(result["ok"])
        worker = next(
            item for item in result["nodes"] if item["name"] == "worker-node-1"
        )
        self.assertEqual(worker["probes"]["overlay"]["status"], "duplicate")

    def test_latency_matrix_parses_loss_percentiles_and_uses_overlay_ip(self):
        calls = []

        def commands(args, timeout):
            calls.append(args)
            if args[1] == "exec":
                return {
                    "ok": False,
                    "command": "kubectl exec",
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "192.0.2.24 : 1.000 - 3.000",
                }
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.latency_matrix(
                plane="overlay",
                source_nodes=["worker-node-1"],
                target_nodes=["worker-node-2"],
                count=3,
            )

        self.assertTrue(result["ok"])
        pair = result["results"][0]
        self.assertEqual(pair["target_address"], "192.0.2.24")
        self.assertEqual(pair["sent"], 3)
        self.assertEqual(pair["received"], 2)
        self.assertAlmostEqual(pair["packet_loss_percent"], 33.333)
        self.assertEqual(pair["rtt_samples_ms"], [1.0, None, 3.0])
        self.assertAlmostEqual(pair["rtt_ms"]["p50"], 2.0)
        self.assertAlmostEqual(pair["rtt_ms"]["p95"], 2.9)
        exec_args = next(args for args in calls if args[1] == "exec")
        self.assertEqual(exec_args[-1], "192.0.2.24")
        self._assert_tokenized_command(exec_args)

    def test_latency_matrix_uses_node_ip_for_underlay(self):
        calls = []

        def commands(args, timeout):
            calls.append(args)
            if args[1] == "exec":
                return {
                    "ok": True,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "192.0.2.4 : 0.700 0.900",
                }
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.latency_matrix(
                plane="underlay",
                source_nodes=["worker-node-1"],
                target_nodes=["worker-node-2"],
                count=2,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["target_address"], "192.0.2.4")
        exec_args = next(args for args in calls if args[1] == "exec")
        self.assertIn("underlay-worker-node-1", exec_args)

    def test_latency_matrix_preserves_partial_results(self):
        def commands(args, timeout):
            if args[1] == "exec":
                return {
                    "ok": True,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "192.0.2.25 : 1.000",
                }
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.latency_matrix(
                plane="overlay",
                source_nodes=["worker-node-1"],
                target_nodes=["worker-node-1", "worker-node-2"],
                count=1,
                include_self=True,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["successful_pairs"], 1)
        self.assertEqual(result["failed_pairs"], 1)
        self.assertEqual(len(result["results"]), 2)

    def test_latency_matrix_reports_command_timeout(self):
        def commands(args, timeout):
            if args[1] == "exec":
                return {
                    "ok": False,
                    "error": "command timed out",
                    "timeout_seconds": timeout,
                }
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.latency_matrix(
                plane="overlay",
                source_nodes=["worker-node-1"],
                target_nodes=["worker-node-2"],
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["failed_pairs"], 1)
        self.assertEqual(
            result["results"][0]["details"]["error"],
            "command timed out",
        )

    def test_bandwidth_enforces_caps_before_running_commands(self):
        with patch("tools.network.run_command") as run:
            duration_result = self.tool.bandwidth(
                source_node="worker-node-1",
                target_node="worker-node-2",
                duration_seconds=11,
            )
            bitrate_result = self.tool.bandwidth(
                source_node="worker-node-1",
                target_node="worker-node-2",
                bitrate_mbps=101,
            )
            same_node_result = self.tool.bandwidth(
                source_node="worker-node-1",
                target_node="worker-node-1",
            )

        self.assertFalse(duration_result["ok"])
        self.assertFalse(bitrate_result["ok"])
        self.assertFalse(same_node_result["ok"])
        run.assert_not_called()

    def test_bandwidth_parses_iperf_and_builds_a_capped_command(self):
        calls = []
        iperf_data = {
            "end": {
                "sum_sent": {
                    "seconds": 5,
                    "bytes": 30000000,
                    "bits_per_second": 48000000,
                    "retransmits": 2,
                },
                "sum_received": {
                    "seconds": 5,
                    "bytes": 29500000,
                    "bits_per_second": 47200000,
                },
            }
        }

        def commands(args, timeout):
            calls.append(args)
            if args[1] == "exec":
                return self._success(iperf_data)
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.bandwidth(
                source_node="worker-node-1",
                target_node="worker-node-2",
                plane="overlay",
                duration_seconds=5,
                bitrate_mbps=50,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["megabits_per_second"], 47.2)
        self.assertEqual(result["summary"]["retransmits"], 2)
        exec_args = next(args for args in calls if args[1] == "exec")
        self.assertIn("--parallel", exec_args)
        self.assertEqual(exec_args[exec_args.index("--parallel") + 1], "1")
        self.assertEqual(exec_args[exec_args.index("--bitrate") + 1], "50M")
        self._assert_tokenized_command(exec_args)

    def test_bandwidth_reports_malformed_iperf_output(self):
        def commands(args, timeout):
            if args[1] == "exec":
                return {
                    "ok": False,
                    "returncode": 1,
                    "stdout": "not-json",
                    "stderr": "iperf failed",
                }
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.bandwidth(
                source_node="worker-node-1",
                target_node="worker-node-2",
            )

        self.assertFalse(result["ok"])
        self.assertIn("not valid JSON", result["error"])
        self.assertEqual(result["details"]["stderr"], "iperf failed")

    def test_path_parses_mtr_hops(self):
        calls = []
        mtr_data = {
            "report": {
                "hubs": [
                    {
                        "count": 1,
                        "host": "192.0.2.26",
                        "Loss%": 0.0,
                        "Snt": 5,
                        "Last": 0.3,
                        "Avg": 0.4,
                        "Best": 0.2,
                        "Wrst": 0.8,
                        "StDev": 0.2,
                    }
                ]
            }
        }

        def commands(args, timeout):
            calls.append(args)
            if args[1] == "exec":
                return self._success(mtr_data)
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.path(
                source_node="worker-node-1",
                target_node="worker-node-2",
                protocol="tcp",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["hops"][0]["host"], "192.0.2.26")
        self.assertEqual(result["hops"][0]["average_ms"], 0.4)
        exec_args = next(args for args in calls if args[1] == "exec")
        self.assertLess(exec_args.index("--report"), exec_args.index("--json"))

    def test_dns_restricts_queries_and_parses_answers(self):
        with patch("tools.network.run_command") as run:
            rejected = self.tool.dns(
                source_node="worker-node-1",
                query="example.com",
            )
        self.assertFalse(rejected["ok"])
        run.assert_not_called()

        dig_output = """; <<>> DiG <<>> frontend.online-boutique.svc.cluster.local A
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1
;; ANSWER SECTION:
frontend.online-boutique.svc.cluster.local. 30 IN A 192.0.2.27

;; Query time: 2 msec
;; SERVER: 192.0.2.28#53(192.0.2.28) (UDP)
"""

        def commands(args, timeout):
            if args[1] == "exec":
                return {
                    "ok": True,
                    "returncode": 0,
                    "stdout": dig_output,
                    "stderr": "",
                }
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.dns(
                source_node="worker-node-1",
                query="frontend.online-boutique.svc.cluster.local",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "NOERROR")
        self.assertEqual(result["query_time_ms"], 2)
        self.assertEqual(result["answers"][0]["value"], "192.0.2.27")

    def test_tcp_connect_validates_service_port_and_parses_attempts(self):
        calls = []
        service_data = {
            "metadata": {"name": "frontend"},
            "spec": {"ports": [{"name": "http", "port": 80}]},
        }
        attempts = [
            {"attempt": 1, "ok": True, "connect_ms": 1.2},
            {"attempt": 2, "ok": True, "connect_ms": 1.8},
            {"attempt": 3, "ok": False, "connect_ms": 2000, "error": "timed out"},
        ]

        def commands(args, timeout):
            calls.append(args)
            if args[1:3] == ["get", "service"]:
                return self._success(service_data)
            if args[1] == "exec":
                return self._success(attempts)
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands):
            result = self.tool.tcp_connect(
                source_node="worker-node-1",
                namespace="online-boutique",
                service="frontend",
                port=80,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["successful_attempts"], 2)
        self.assertEqual(result["failed_attempts"], 1)
        self.assertEqual(result["connect_ms"]["mean"], 1.5)
        exec_args = next(args for args in calls if args[1] == "exec")
        self.assertEqual(
            exec_args[-4],
            "frontend.online-boutique.svc.cluster.local",
        )
        self._assert_tokenized_command(exec_args)

    def test_tcp_connect_rejects_undeclared_service_port(self):
        service_data = {"spec": {"ports": [{"port": 80}]}}

        def commands(args, timeout):
            if args[1:3] == ["get", "service"]:
                return self._success(service_data)
            return self._inventory_commands(args, timeout)

        with patch("tools.network.run_command", side_effect=commands) as run:
            result = self.tool.tcp_connect(
                source_node="worker-node-1",
                namespace="online-boutique",
                service="frontend",
                port=443,
            )

        self.assertFalse(result["ok"])
        self.assertIn("not declared", result["error"])
        self.assertFalse(any(call.args[0][1] == "exec" for call in run.mock_calls))

    def test_unknown_or_non_worker_node_is_rejected(self):
        with patch(
            "tools.network.run_command",
            side_effect=self._inventory_commands,
        ):
            result = self.tool.latency_matrix(
                plane="overlay",
                source_nodes=["master-node-1"],
                target_nodes=["worker-node-1"],
            )

        self.assertFalse(result["ok"])
        self.assertIn("role=services", result["errors"][0]["error"])

    def _inventory_commands(self, args, timeout):
        if args[1:3] == ["get", "nodes"]:
            return self._success({"items": self._nodes()})
        if self._is_pod_inventory(args, "overlay"):
            return self._success({"items": self._pods("overlay")})
        if self._is_pod_inventory(args, "underlay"):
            return self._success({"items": self._pods("underlay")})
        raise AssertionError(f"unexpected command: {args}")

    def _is_pod_inventory(self, args, plane):
        return (
            args[1:3] == ["get", "pods"]
            and f"app.kubernetes.io/component={plane}" in args[args.index("-l") + 1]
        )

    def _nodes(self):
        return [
            self._node(
                "worker-node-1",
                "192.0.2.3",
                "192.0.2.22/24",
            ),
            self._node(
                "worker-node-2",
                "192.0.2.4",
                "192.0.2.29/24",
            ),
        ]

    def _node(self, name, internal_ip, pod_cidr):
        return {
            "metadata": {"name": name},
            "spec": {"podCIDR": pod_cidr},
            "status": {
                "addresses": [
                    {"type": "InternalIP", "address": internal_ip},
                ],
                "conditions": [
                    {"type": "Ready", "status": "True"},
                ],
            },
        }

    def _pods(self, plane):
        return [
            self._pod(
                f"{plane}-worker-node-1",
                "worker-node-1",
                "192.0.2.25" if plane == "overlay" else "192.0.2.3",
            ),
            self._pod(
                f"{plane}-worker-node-2",
                "worker-node-2",
                "192.0.2.24" if plane == "overlay" else "192.0.2.4",
            ),
        ]

    def _pod(self, name, node, pod_ip):
        return {
            "metadata": {"name": name},
            "spec": {"nodeName": node},
            "status": {
                "phase": "Running",
                "podIP": pod_ip,
                "conditions": [
                    {"type": "Ready", "status": "True"},
                ],
            },
        }

    def _success(self, data):
        return {
            "ok": True,
            "command": "kubectl",
            "returncode": 0,
            "stdout": json.dumps(data),
            "stderr": "",
        }

    def _assert_tokenized_command(self, args):
        self.assertIsInstance(args, list)
        for operator in ["|", "&&", "||", ";", ">", ">>", "<"]:
            self.assertNotIn(operator, args)
