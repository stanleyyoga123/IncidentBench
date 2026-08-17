import json
import math
import re
import statistics
from typing import Any

from tools.utility import run_command


class NetworkTool:
    _PLANES = {"overlay", "underlay"}
    _DNS_RECORD_TYPES = {"A", "AAAA", "SRV"}
    _BANDWIDTH_PROTOCOLS = {"tcp", "udp"}
    _BANDWIDTH_DIRECTIONS = {"forward", "reverse", "bidirectional"}
    _PATH_PROTOCOLS = {"icmp", "tcp"}
    _DNS_LABEL_PATTERN = re.compile(
        r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
        re.IGNORECASE,
    )
    _DNS_QUERY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
    _TCP_PROBE_SCRIPT = """import json
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
attempts = int(sys.argv[3])
timeout = float(sys.argv[4])
results = []
for attempt in range(1, attempts + 1):
    started = time.perf_counter()
    try:
        connection = socket.create_connection((host, port), timeout=timeout)
        connection.close()
        results.append({
            "attempt": attempt,
            "ok": True,
            "connect_ms": round((time.perf_counter() - started) * 1000, 3),
        })
    except Exception as exc:
        results.append({
            "attempt": attempt,
            "ok": False,
            "connect_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": str(exc)[:300],
        })
print(json.dumps(results))
"""

    def __init__(
        self,
        path: str = "kubectl",
        namespace: str = "utility",
        overlay_selector: str = (
            "app.kubernetes.io/name=cloudagent-network-probe,"
            "app.kubernetes.io/component=overlay"
        ),
        underlay_selector: str = (
            "app.kubernetes.io/name=cloudagent-network-probe,"
            "app.kubernetes.io/component=underlay"
        ),
        timeout_seconds: int = 30,
        max_duration_seconds: int = 10,
        max_bitrate_mbps: int = 100,
        max_matrix_nodes: int = 6,
    ) -> None:
        self.kubectl_path = path
        self.namespace = namespace
        self.selectors = {
            "overlay": overlay_selector,
            "underlay": underlay_selector,
        }
        self.timeout_seconds = timeout_seconds
        self.max_duration_seconds = max_duration_seconds
        self.max_bitrate_mbps = max_bitrate_mbps
        self.max_matrix_nodes = max_matrix_nodes

    def topology(self, plane: str = "both") -> dict[str, Any]:
        planes = self._selected_planes(plane, allow_both=True)
        inventory = self._inventory(planes)
        if not inventory.get("ok"):
            return self._action_error("topology", inventory)

        results = []
        ready_probe_count = 0
        expected_probe_count = len(inventory["nodes"]) * len(planes)
        for node_name, node in sorted(inventory["nodes"].items()):
            probes = {}
            for selected_plane in planes:
                candidates = inventory["probes"][selected_plane].get(node_name, [])
                status = self._probe_status(candidates)
                if status == "ready":
                    ready_probe_count += 1
                probes[selected_plane] = {
                    "status": status,
                    "count": len(candidates),
                    "pods": candidates,
                }
            results.append({**node, "probes": probes})

        ok = ready_probe_count == expected_probe_count
        return {
            "ok": ok,
            "partial": 0 < ready_probe_count < expected_probe_count,
            "action": "topology",
            "namespace": self.namespace,
            "planes": planes,
            "worker_count": len(inventory["nodes"]),
            "expected_probe_count": expected_probe_count,
            "ready_probe_count": ready_probe_count,
            "nodes": results,
        }

    def latency_matrix(
        self,
        plane: str = "both",
        source_nodes: list[str] | None = None,
        target_nodes: list[str] | None = None,
        count: int = 5,
        include_self: bool = False,
    ) -> dict[str, Any]:
        planes = self._selected_planes(plane, allow_both=True)
        if count < 1 or count > 10:
            return self._error(
                "latency_matrix",
                "count must be between 1 and 10",
            )

        inventory = self._inventory(planes)
        if not inventory.get("ok"):
            return self._action_error("latency_matrix", inventory)

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for selected_plane in planes:
            resolved = self._resolve_matrix_nodes(
                inventory,
                selected_plane,
                source_nodes,
                target_nodes,
            )
            if not resolved.get("ok"):
                errors.append(
                    {
                        "plane": selected_plane,
                        "error": resolved["error"],
                    }
                )
                continue

            for source_node in resolved["source_nodes"]:
                source_probe = self._ready_probe(
                    inventory,
                    selected_plane,
                    source_node,
                )
                target_pairs = []
                for target_node in resolved["target_nodes"]:
                    if not include_self and source_node == target_node:
                        continue
                    target = self._target_address(
                        inventory,
                        selected_plane,
                        target_node,
                    )
                    target_pairs.append((target_node, target))
                if not target_pairs:
                    continue
                command_result = self._exec_probe(
                    source_probe["name"],
                    [
                        "fping",
                        "-C",
                        str(count),
                        "-q",
                        "-p",
                        "200",
                        "-t",
                        "1000",
                        *[target for _, target in target_pairs],
                    ],
                )
                for target_node, target in target_pairs:
                    results.append(
                        self._latency_result(
                            command_result,
                            selected_plane,
                            source_node,
                            target_node,
                            target,
                            count,
                        )
                    )

        successful = sum(1 for item in results if item.get("ok"))
        failed = len(results) - successful + len(errors)
        return {
            "ok": failed == 0,
            "partial": successful > 0 and failed > 0,
            "action": "latency_matrix",
            "planes": planes,
            "count": count,
            "include_self": include_self,
            "pair_count": len(results),
            "successful_pairs": successful,
            "failed_pairs": failed,
            "errors": errors,
            "results": results,
        }

    def bandwidth(
        self,
        source_node: str,
        target_node: str,
        plane: str = "overlay",
        protocol: str = "tcp",
        direction: str = "forward",
        duration_seconds: int = 5,
        bitrate_mbps: int = 50,
    ) -> dict[str, Any]:
        selected_plane = self._selected_planes(plane)[0]
        protocol = protocol.lower()
        direction = direction.lower()
        if protocol not in self._BANDWIDTH_PROTOCOLS:
            return self._error(
                "bandwidth",
                "protocol must be tcp or udp",
            )
        if direction not in self._BANDWIDTH_DIRECTIONS:
            return self._error(
                "bandwidth",
                "direction must be forward, reverse, or bidirectional",
            )
        if source_node == target_node:
            return self._error(
                "bandwidth",
                "source_node and target_node must be different",
            )
        if duration_seconds < 1 or duration_seconds > self.max_duration_seconds:
            return self._error(
                "bandwidth",
                f"duration_seconds must be between 1 and {self.max_duration_seconds}",
            )
        if bitrate_mbps < 1 or bitrate_mbps > self.max_bitrate_mbps:
            return self._error(
                "bandwidth",
                f"bitrate_mbps must be between 1 and {self.max_bitrate_mbps}",
            )

        inventory = self._inventory([selected_plane])
        if not inventory.get("ok"):
            return self._action_error("bandwidth", inventory)
        validation = self._validate_requested_nodes(
            inventory,
            selected_plane,
            [source_node, target_node],
        )
        if validation:
            return self._error("bandwidth", validation)

        source_probe = self._ready_probe(inventory, selected_plane, source_node)
        target = self._target_address(
            inventory,
            selected_plane,
            target_node,
        )
        args = [
            "iperf3",
            "--client",
            target,
            "--port",
            "5201",
            "--time",
            str(duration_seconds),
            "--parallel",
            "1",
            "--bitrate",
            f"{bitrate_mbps}M",
            "--json",
        ]
        if protocol == "udp":
            args.append("--udp")
        if direction == "reverse":
            args.append("--reverse")
        elif direction == "bidirectional":
            args.append("--bidir")

        command_result = self._exec_probe(
            source_probe["name"],
            args,
            timeout_seconds=min(
                self.timeout_seconds,
                duration_seconds + 10,
            ),
        )
        parsed = self._load_command_json(command_result)
        if not parsed.get("ok"):
            return {
                "ok": False,
                "action": "bandwidth",
                "plane": selected_plane,
                "source_node": source_node,
                "target_node": target_node,
                "protocol": protocol,
                "direction": direction,
                "error": parsed["error"],
                "details": self._command_details(command_result),
            }
        if parsed["data"].get("error"):
            return {
                "ok": False,
                "action": "bandwidth",
                "plane": selected_plane,
                "source_node": source_node,
                "target_node": target_node,
                "protocol": protocol,
                "direction": direction,
                "error": str(parsed["data"]["error"])[:1000],
            }

        return {
            "ok": True,
            "action": "bandwidth",
            "plane": selected_plane,
            "source_node": source_node,
            "target_node": target_node,
            "target_address": target,
            "protocol": protocol,
            "direction": direction,
            "duration_seconds": duration_seconds,
            "parallel_streams": 1,
            "bitrate_limit_mbps": bitrate_mbps,
            "summary": self._iperf_summary(parsed["data"], protocol),
        }

    def path(
        self,
        source_node: str,
        target_node: str,
        plane: str = "overlay",
        protocol: str = "icmp",
        cycles: int = 5,
    ) -> dict[str, Any]:
        selected_plane = self._selected_planes(plane)[0]
        protocol = protocol.lower()
        if protocol not in self._PATH_PROTOCOLS:
            return self._error("path", "protocol must be icmp or tcp")
        if cycles < 1 or cycles > 10:
            return self._error("path", "cycles must be between 1 and 10")

        inventory = self._inventory([selected_plane])
        if not inventory.get("ok"):
            return self._action_error("path", inventory)
        validation = self._validate_requested_nodes(
            inventory,
            selected_plane,
            [source_node, target_node],
        )
        if validation:
            return self._error("path", validation)

        source_probe = self._ready_probe(inventory, selected_plane, source_node)
        target = self._target_address(
            inventory,
            selected_plane,
            target_node,
        )
        args = [
            "mtr",
            "--report",
            "--json",
            "--report-cycles",
            str(cycles),
        ]
        if protocol == "tcp":
            args.extend(["--tcp", "--port", "5201"])
        args.append(target)
        command_result = self._exec_probe(source_probe["name"], args)
        parsed = self._load_command_json(command_result)
        if not parsed.get("ok"):
            return {
                "ok": False,
                "action": "path",
                "plane": selected_plane,
                "source_node": source_node,
                "target_node": target_node,
                "error": parsed["error"],
                "details": self._command_details(command_result),
            }

        report = parsed["data"].get("report") or {}
        hubs = report.get("hubs") or []
        return {
            "ok": True,
            "action": "path",
            "plane": selected_plane,
            "source_node": source_node,
            "target_node": target_node,
            "target_address": target,
            "protocol": protocol,
            "cycles": cycles,
            "hops": [self._mtr_hop(hop) for hop in hubs],
        }

    def dns(
        self,
        source_node: str,
        query: str,
        plane: str = "overlay",
        record_type: str = "A",
        timeout_seconds: int = 2,
        retries: int = 1,
    ) -> dict[str, Any]:
        selected_plane = self._selected_planes(plane)[0]
        record_type = record_type.upper()
        query = query.rstrip(".")
        validation = self._dns_query_error(query)
        if validation:
            return self._error("dns", validation)
        if record_type not in self._DNS_RECORD_TYPES:
            return self._error("dns", "record_type must be A, AAAA, or SRV")
        if timeout_seconds < 1 or timeout_seconds > 5:
            return self._error("dns", "timeout_seconds must be between 1 and 5")
        if retries < 1 or retries > 2:
            return self._error("dns", "retries must be between 1 and 2")

        inventory = self._inventory([selected_plane])
        if not inventory.get("ok"):
            return self._action_error("dns", inventory)
        validation = self._validate_requested_nodes(
            inventory,
            selected_plane,
            [source_node],
        )
        if validation:
            return self._error("dns", validation)

        source_probe = self._ready_probe(inventory, selected_plane, source_node)
        command_result = self._exec_probe(
            source_probe["name"],
            [
                "dig",
                f"+time={timeout_seconds}",
                f"+tries={retries}",
                query,
                record_type,
            ],
            timeout_seconds=min(
                self.timeout_seconds,
                timeout_seconds * retries + 5,
            ),
        )
        parsed = self._parse_dig(
            command_result.get("stdout", ""),
        )
        if not parsed.get("parsed"):
            return {
                "ok": False,
                "action": "dns",
                "plane": selected_plane,
                "source_node": source_node,
                "query": query,
                "record_type": record_type,
                "error": "dig output could not be parsed",
                "details": self._command_details(command_result),
            }
        return {
            "ok": parsed["status"] == "NOERROR",
            "action": "dns",
            "plane": selected_plane,
            "source_node": source_node,
            "query": query,
            "record_type": record_type,
            "status": parsed["status"],
            "resolver": parsed["resolver"],
            "query_time_ms": parsed["query_time_ms"],
            "answers": parsed["answers"],
            "error": (
                None
                if parsed["status"] == "NOERROR"
                else f"DNS response status was {parsed['status']}"
            ),
        }

    def tcp_connect(
        self,
        source_node: str,
        namespace: str,
        service: str,
        port: int,
        plane: str = "overlay",
        attempts: int = 3,
        timeout_seconds: int = 2,
    ) -> dict[str, Any]:
        selected_plane = self._selected_planes(plane)[0]
        for field_name, value in [
            ("namespace", namespace),
            ("service", service),
        ]:
            if not self._DNS_LABEL_PATTERN.fullmatch(value):
                return self._error(
                    "tcp_connect",
                    f"{field_name} must be a valid Kubernetes DNS label",
                )
        if port < 1 or port > 65535:
            return self._error("tcp_connect", "port must be between 1 and 65535")
        if attempts < 1 or attempts > 5:
            return self._error("tcp_connect", "attempts must be between 1 and 5")
        if timeout_seconds < 1 or timeout_seconds > 5:
            return self._error(
                "tcp_connect",
                "timeout_seconds must be between 1 and 5",
            )

        inventory = self._inventory([selected_plane])
        if not inventory.get("ok"):
            return self._action_error("tcp_connect", inventory)
        validation = self._validate_requested_nodes(
            inventory,
            selected_plane,
            [source_node],
        )
        if validation:
            return self._error("tcp_connect", validation)

        service_result = run_command(
            [
                self.kubectl_path,
                "get",
                "service",
                service,
                "-n",
                namespace,
                "-o",
                "json",
            ],
            self.timeout_seconds,
        )
        parsed_service = self._load_command_json(service_result)
        if not parsed_service.get("ok"):
            return {
                "ok": False,
                "action": "tcp_connect",
                "error": "service could not be read",
                "details": self._command_details(service_result),
            }
        declared_ports = {
            item.get("port")
            for item in (parsed_service["data"].get("spec") or {}).get("ports", [])
        }
        if port not in declared_ports:
            return self._error(
                "tcp_connect",
                f"port {port} is not declared by service {namespace}/{service}",
            )

        source_probe = self._ready_probe(inventory, selected_plane, source_node)
        host = f"{service}.{namespace}.svc.cluster.local"
        command_result = self._exec_probe(
            source_probe["name"],
            [
                "python3",
                "-c",
                self._TCP_PROBE_SCRIPT,
                host,
                str(port),
                str(attempts),
                str(timeout_seconds),
            ],
            timeout_seconds=min(
                self.timeout_seconds,
                attempts * timeout_seconds + 5,
            ),
        )
        parsed = self._load_command_json(command_result)
        if not parsed.get("ok") or not isinstance(parsed.get("data"), list):
            return {
                "ok": False,
                "action": "tcp_connect",
                "plane": selected_plane,
                "source_node": source_node,
                "service": f"{namespace}/{service}",
                "port": port,
                "error": "TCP probe output could not be parsed",
                "details": self._command_details(command_result),
            }

        attempt_results = parsed["data"]
        successful_times = [
            float(item["connect_ms"])
            for item in attempt_results
            if item.get("ok") and item.get("connect_ms") is not None
        ]
        success_count = len(successful_times)
        return {
            "ok": success_count == attempts,
            "partial": 0 < success_count < attempts,
            "action": "tcp_connect",
            "plane": selected_plane,
            "source_node": source_node,
            "service": f"{namespace}/{service}",
            "host": host,
            "port": port,
            "attempt_count": attempts,
            "successful_attempts": success_count,
            "failed_attempts": attempts - success_count,
            "connect_ms": self._sample_summary(successful_times),
            "attempts": attempt_results,
        }

    def _inventory(self, planes: list[str]) -> dict[str, Any]:
        node_result = run_command(
            [
                self.kubectl_path,
                "get",
                "nodes",
                "-l",
                "role=services",
                "-o",
                "json",
            ],
            self.timeout_seconds,
        )
        parsed_nodes = self._load_command_json(node_result)
        if not parsed_nodes.get("ok"):
            return {
                "ok": False,
                "error": "worker node inventory could not be read",
                "details": self._command_details(node_result),
            }

        nodes = {}
        for item in parsed_nodes["data"].get("items", []):
            name = (item.get("metadata") or {}).get("name")
            if not name:
                continue
            status = item.get("status") or {}
            addresses = {
                address.get("type"): address.get("address")
                for address in status.get("addresses", [])
            }
            conditions = {
                condition.get("type"): condition.get("status")
                for condition in status.get("conditions", [])
            }
            nodes[name] = {
                "name": name,
                "ready": conditions.get("Ready") == "True",
                "internal_ip": addresses.get("InternalIP"),
                "pod_cidr": (item.get("spec") or {}).get("podCIDR"),
            }

        probes: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for plane in planes:
            pod_result = run_command(
                [
                    self.kubectl_path,
                    "get",
                    "pods",
                    "-n",
                    self.namespace,
                    "-l",
                    self.selectors[plane],
                    "-o",
                    "json",
                ],
                self.timeout_seconds,
            )
            parsed_pods = self._load_command_json(pod_result)
            if not parsed_pods.get("ok"):
                return {
                    "ok": False,
                    "error": f"{plane} probe inventory could not be read",
                    "details": self._command_details(pod_result),
                }
            probes[plane] = {}
            for item in parsed_pods["data"].get("items", []):
                metadata = item.get("metadata") or {}
                spec = item.get("spec") or {}
                status = item.get("status") or {}
                node_name = spec.get("nodeName")
                if not node_name or metadata.get("deletionTimestamp"):
                    continue
                conditions = {
                    condition.get("type"): condition.get("status")
                    for condition in status.get("conditions", [])
                }
                probes[plane].setdefault(node_name, []).append(
                    {
                        "name": metadata.get("name"),
                        "pod_ip": status.get("podIP"),
                        "phase": status.get("phase"),
                        "ready": (
                            status.get("phase") == "Running"
                            and conditions.get("Ready") == "True"
                        ),
                    }
                )

        return {
            "ok": True,
            "nodes": nodes,
            "probes": probes,
        }

    def _resolve_matrix_nodes(
        self,
        inventory: dict[str, Any],
        plane: str,
        source_nodes: list[str] | None,
        target_nodes: list[str] | None,
    ) -> dict[str, Any]:
        healthy = sorted(
            node_name
            for node_name, node in inventory["nodes"].items()
            if node.get("ready")
            and self._probe_status(
                inventory["probes"][plane].get(node_name, [])
            )
            == "ready"
        )
        sources = self._unique(source_nodes or healthy)
        targets = self._unique(target_nodes or healthy)
        if not sources or not targets:
            return {
                "ok": False,
                "error": (
                    f"no healthy {plane} probe pairs are available; "
                    "probe absence is missing evidence"
                ),
            }
        if len(set(sources + targets)) > self.max_matrix_nodes:
            return {
                "ok": False,
                "error": (
                    "latency matrix includes more than "
                    f"{self.max_matrix_nodes} distinct nodes"
                ),
            }
        validation = self._validate_requested_nodes(
            inventory,
            plane,
            sources + targets,
        )
        if validation:
            return {"ok": False, "error": validation}
        return {
            "ok": True,
            "source_nodes": sources,
            "target_nodes": targets,
        }

    def _validate_requested_nodes(
        self,
        inventory: dict[str, Any],
        plane: str,
        node_names: list[str],
    ) -> str | None:
        for node_name in self._unique(node_names):
            node = inventory["nodes"].get(node_name)
            if not node:
                return (
                    f"node {node_name} is not a worker selected by role=services"
                )
            if not node.get("ready"):
                return f"node {node_name} is not Ready"
            status = self._probe_status(
                inventory["probes"][plane].get(node_name, [])
            )
            if status != "ready":
                return (
                    f"{plane} probe for node {node_name} is {status}; "
                    "probe absence is missing evidence"
                )
        return None

    def _selected_planes(
        self,
        plane: str,
        allow_both: bool = False,
    ) -> list[str]:
        normalized = plane.lower()
        if allow_both and normalized == "both":
            return ["overlay", "underlay"]
        if normalized not in self._PLANES:
            expected = "overlay, underlay, or both" if allow_both else "overlay or underlay"
            raise ValueError(f"plane must be {expected}")
        return [normalized]

    def _ready_probe(
        self,
        inventory: dict[str, Any],
        plane: str,
        node_name: str,
    ) -> dict[str, Any]:
        return next(
            probe
            for probe in inventory["probes"][plane][node_name]
            if probe.get("ready")
        )

    def _target_address(
        self,
        inventory: dict[str, Any],
        plane: str,
        node_name: str,
    ) -> str:
        if plane == "underlay":
            address = inventory["nodes"][node_name].get("internal_ip")
        else:
            address = self._ready_probe(
                inventory,
                plane,
                node_name,
            ).get("pod_ip")
        if not address:
            raise ValueError(f"{plane} target address missing for node {node_name}")
        return str(address)

    def _probe_status(self, probes: list[dict[str, Any]]) -> str:
        ready = [probe for probe in probes if probe.get("ready")]
        if len(ready) == 1 and len(probes) == 1:
            return "ready"
        if len(ready) > 1 or len(probes) > 1:
            return "duplicate"
        if probes:
            return "not_ready"
        return "missing"

    def _exec_probe(
        self,
        pod_name: str,
        args: list[str],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        return run_command(
            [
                self.kubectl_path,
                "exec",
                "-n",
                self.namespace,
                pod_name,
                "--",
                *args,
            ],
            timeout_seconds or self.timeout_seconds,
        )

    def _latency_result(
        self,
        command_result: dict[str, Any],
        plane: str,
        source_node: str,
        target_node: str,
        target: str,
        count: int,
    ) -> dict[str, Any]:
        text = "\n".join(
            value
            for value in [
                command_result.get("stdout", ""),
                command_result.get("stderr", ""),
            ]
            if value
        )
        samples = self._parse_fping_samples(text, target)
        if samples is None or len(samples) != count:
            return {
                "ok": False,
                "plane": plane,
                "source_node": source_node,
                "target_node": target_node,
                "target_address": target,
                "error": "fping output could not be parsed",
                "details": self._command_details(command_result),
            }
        received = [sample for sample in samples if sample is not None]
        return {
            "ok": True,
            "reachable": bool(received),
            "plane": plane,
            "source_node": source_node,
            "target_node": target_node,
            "target_address": target,
            "sent": count,
            "received": len(received),
            "packet_loss_percent": round(
                (count - len(received)) / count * 100,
                3,
            ),
            "rtt_samples_ms": samples,
            "rtt_ms": self._sample_summary(received),
        }

    def _parse_fping_samples(
        self,
        text: str,
        target: str,
    ) -> list[float | None] | None:
        for line in reversed(text.splitlines()):
            if ":" not in line:
                continue
            prefix, _, values = line.partition(":")
            if prefix.strip() != target:
                continue
            samples: list[float | None] = []
            for value in values.split():
                if value == "-":
                    samples.append(None)
                    continue
                try:
                    samples.append(float(value))
                except ValueError:
                    return None
            return samples or None
        return None

    def _sample_summary(self, samples: list[float]) -> dict[str, float] | None:
        if not samples:
            return None
        ordered = sorted(samples)
        return {
            "min": round(ordered[0], 3),
            "mean": round(statistics.fmean(ordered), 3),
            "p50": round(self._percentile(ordered, 50), 3),
            "p95": round(self._percentile(ordered, 95), 3),
            "max": round(ordered[-1], 3),
            "jitter": round(
                statistics.pstdev(ordered) if len(ordered) > 1 else 0.0,
                3,
            ),
        }

    def _percentile(self, ordered: list[float], percentile: int) -> float:
        if len(ordered) == 1:
            return ordered[0]
        rank = (len(ordered) - 1) * percentile / 100
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return ordered[lower]
        weight = rank - lower
        return ordered[lower] * (1 - weight) + ordered[upper] * weight

    def _iperf_summary(
        self,
        data: dict[str, Any],
        protocol: str,
    ) -> dict[str, Any]:
        end = data.get("end") or {}
        streams = {}
        for name, value in end.items():
            if not name.startswith("sum") or not isinstance(value, dict):
                continue
            summary = {}
            for source_key, output_key in [
                ("seconds", "seconds"),
                ("bytes", "bytes"),
                ("bits_per_second", "bits_per_second"),
                ("retransmits", "retransmits"),
                ("jitter_ms", "jitter_ms"),
                ("lost_packets", "lost_packets"),
                ("packets", "packets"),
                ("lost_percent", "lost_percent"),
            ]:
                if value.get(source_key) is not None:
                    summary[output_key] = value[source_key]
            if value.get("bits_per_second") is not None:
                summary["megabits_per_second"] = round(
                    float(value["bits_per_second"]) / 1_000_000,
                    3,
                )
            streams[name] = summary

        primary = (
            streams.get("sum_received")
            or streams.get("sum")
            or streams.get("sum_sent")
            or {}
        )
        return {
            "protocol": protocol,
            "megabits_per_second": primary.get("megabits_per_second"),
            "bytes": primary.get("bytes"),
            "retransmits": (
                (streams.get("sum_sent") or {}).get("retransmits")
                if protocol == "tcp"
                else None
            ),
            "jitter_ms": primary.get("jitter_ms"),
            "lost_packets": primary.get("lost_packets"),
            "packets": primary.get("packets"),
            "lost_percent": primary.get("lost_percent"),
            "streams": streams,
        }

    def _mtr_hop(self, hop: dict[str, Any]) -> dict[str, Any]:
        def value(*keys: str) -> Any:
            for key in keys:
                if hop.get(key) is not None:
                    return hop[key]
            return None

        return {
            "hop": value("count"),
            "host": value("host"),
            "loss_percent": value("Loss%", "loss"),
            "sent": value("Snt", "sent"),
            "last_ms": value("Last", "last"),
            "average_ms": value("Avg", "avg"),
            "best_ms": value("Best", "best"),
            "worst_ms": value("Wrst", "worst"),
            "standard_deviation_ms": value("StDev", "stdev"),
        }

    def _parse_dig(self, text: str) -> dict[str, Any]:
        status_match = re.search(r"status:\s*([A-Z]+)", text)
        query_time_match = re.search(r"Query time:\s*(\d+)\s*msec", text)
        resolver_match = re.search(r"SERVER:\s*([^\s#]+(?:#[0-9]+)?)", text)
        answers = []
        in_answers = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == ";; ANSWER SECTION:":
                in_answers = True
                continue
            if in_answers and stripped.startswith(";;"):
                break
            if not in_answers or not stripped:
                continue
            parts = stripped.split(None, 4)
            if len(parts) == 5:
                answers.append(
                    {
                        "name": parts[0].rstrip("."),
                        "ttl": int(parts[1]) if parts[1].isdigit() else parts[1],
                        "class": parts[2],
                        "type": parts[3],
                        "value": parts[4].rstrip("."),
                    }
                )
        return {
            "parsed": status_match is not None,
            "status": status_match.group(1) if status_match else None,
            "query_time_ms": (
                int(query_time_match.group(1)) if query_time_match else None
            ),
            "resolver": resolver_match.group(1) if resolver_match else None,
            "answers": answers,
        }

    def _dns_query_error(self, query: str) -> str | None:
        if (
            not query
            or len(query) > 253
            or not self._DNS_QUERY_PATTERN.fullmatch(query)
            or ".." in query
            or not query.lower().endswith(".svc.cluster.local")
        ):
            return "query must be a valid Kubernetes service name under svc.cluster.local"
        return None

    def _load_command_json(self, result: dict[str, Any]) -> dict[str, Any]:
        stdout = result.get("stdout", "")
        try:
            data = json.loads(stdout)
        except (TypeError, json.JSONDecodeError):
            return {"ok": False, "error": "command output was not valid JSON"}
        return {"ok": True, "data": data}

    def _command_details(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "returncode": result.get("returncode"),
            "error": self._bounded(result.get("error")),
            "stdout": self._bounded(result.get("stdout")),
            "stderr": self._bounded(result.get("stderr")),
        }

    def _action_error(
        self,
        action: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "action": action,
            "error": result.get("error", "network probe inventory failed"),
            "details": result.get("details"),
        }

    def _error(self, action: str, error: str) -> dict[str, Any]:
        return {
            "ok": False,
            "action": action,
            "error": error,
        }

    def _bounded(self, value: Any, limit: int = 2000) -> Any:
        if not isinstance(value, str) or len(value) <= limit:
            return value
        return value[:limit] + f"...[truncated {len(value) - limit} chars]"

    def _unique(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))
