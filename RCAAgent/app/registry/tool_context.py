DETECTOR_METRIC_REFERENCE = {
    "traffic_rps": ["istio_requests_total"],
    "response_time_p95_seconds": ["istio_request_duration_milliseconds_bucket"],
    "http_5xx_rate": ["istio_requests_total"],
    "app_instance_count": ["kube_deployment_spec_replicas"],
    "deployment_cpu_usage": [
        "container_cpu_usage_seconds_total",
        "kube_pod_owner",
        "kube_replicaset_owner",
    ],
    "deployment_cpu_request_utilization_percent": [
        "container_cpu_usage_seconds_total",
        "kube_pod_container_resource_requests",
        "kube_pod_owner",
        "kube_replicaset_owner",
    ],
    "deployment_memory_request_utilization_percent": [
        "container_memory_working_set_bytes",
        "kube_pod_container_resource_requests",
        "kube_pod_owner",
        "kube_replicaset_owner",
    ],
    "deployment_disk_io_bytes_per_second": [
        "container_fs_reads_bytes_total",
        "container_fs_writes_bytes_total",
        "kube_pod_owner",
        "kube_replicaset_owner",
    ],
    "deployment_network_io_bytes_per_second": [
        "istio_request_bytes_sum",
        "istio_response_bytes_sum",
    ],
    "node_cpu_utilization_percent": ["node_cpu_seconds_total"],
    "node_memory_utilization_percent": [
        "node_memory_MemAvailable_bytes",
        "node_memory_MemTotal_bytes",
    ],
    "node_disk_io_bytes_per_second": [
        "node_disk_read_bytes_total",
        "node_disk_written_bytes_total",
    ],
    "node_network_io_bytes_per_second": [
        "node_network_receive_bytes_total",
        "node_network_transmit_bytes_total",
        "node_network_receive_drop_total",
        "node_network_transmit_drop_total",
        "node_network_receive_errs_total",
        "node_network_transmit_errs_total",
        "node_netstat_Tcp_RetransSegs",
    ],
}


TOOL_USAGE_CONTEXT = {
    "kubectl": [
        "Use for Kubernetes state: pods, deployments, services, endpoints, HPAs, rollout status, node placement, and readiness.",
        "Kubernetes Events are intentionally excluded by cluster policy; do not query them.",
        "Pass only arguments after the kubectl binary, for example `get pods -n <incident-namespace> -o wide`.",
        "Do not use shell pipes or shell operators. Use the tool's `grep` argument for line filtering.",
        "Prefer read-only validation before proposing or relying on any mutation.",
        "Dangerous deletes and scaling workloads to zero are guarded; report blocked tool results as evidence.",
    ],
    "prometheus": [
        "Use for metrics, trends, saturation, latency, request rate, error rate, replica count, node utilization, and detector-window correlation.",
        "Prefer `query_type='instant'` for point checks and `query_type='range'` only when a time window is needed.",
        "Keep range queries bounded, normally 30 minutes or the detector timestamp +/- 15 minutes, with `step` of `30s` or `1m`.",
        "Use the `filter` parameter to keep only relevant metric labels, values, and bounded result counts.",
        "Empty results are missing evidence or a data gap, not proof of health.",
        "For suspected network constraints, correlate demand and latency with node/device throughput, Istio request/response byte rates, TCP retransmits, interface drops/errors, and pod placement. A throughput plateau can matter even when the physical interface is not fully utilized.",
        "Prometheus metric names used by detector signals are listed below. Build focused PromQL from those metric names and the incident labels instead of copying a fixed query.",
    ],
    "loki": [
        "Use for application errors, exceptions, panics, timeouts, retries, connection refused/reset, OOM/restart clues, and request failure messages.",
        "Use bounded LogQL with `since`, `limit`, and `direction`; avoid broad log dumps.",
        "Filter to relevant namespace, app, pod, container, or error text whenever possible.",
        "Use the `filter` parameter to keep only useful streams and log lines.",
        "Report no matching logs as negative or missing evidence with the exact query/window.",
    ],
    "jaeger.list_services": [
        "Use when the exact Jaeger service name is unknown, then pass one of the returned names to `jaeger.retrieve_slow_traces`.",
        "The result reflects services currently present in Jaeger trace storage, which may differ from Kubernetes Service names.",
    ],
    "jaeger.retrieve_slow_traces": [
        "Use first for latency investigations when you need representative slow trace IDs for a service.",
        "Discover the exact service name first; use a bounded `lookback` such as `15m` or `30m` and a small `limit`.",
        "Trace absence is missing evidence unless the query window and service name are confirmed.",
    ],
    "jaeger.investigate_trace": [
        "Use after selecting a trace ID to summarize its root operation, slowest spans, and service duration breakdown.",
    ],
    "jaeger.retrieve_bottleneck": [
        "Use after selecting a trace ID when you need a direct bottleneck candidate.",
        "Treat the result as trace evidence, not absolute proof; compare with metrics, logs, or Kubernetes state when possible.",
    ],
    "network.topology": [
        "Use before active network probes to verify which Ready role=services workers have exactly one healthy overlay and underlay probe.",
        "Missing, duplicate, or unready probes are missing evidence and must not be interpreted as healthy networking.",
    ],
    "network.latency_matrix": [
        "Use for direct node-to-node RTT, jitter, and packet-loss evidence. Compare overlay with underlay to distinguish Flannel VXLAN degradation from the physical node path.",
        "Use a focused source/target subset when the affected nodes are known; use the full matrix only when the common path is unclear.",
        "A reachable result can still be degraded; compare affected pairs with healthy peers and correlate with Prometheus and Jaeger.",
    ],
    "network.bandwidth": [
        "Use only after latency, traces, metrics, or placement provide a concrete bandwidth hypothesis.",
        "This is an active traffic test. Test one source-target pair, keep the default duration and bitrate when possible, and never describe the capped result as physical line rate.",
        "Correlate throughput with retransmits, loss, latency, interface metrics, and application symptoms before concluding that bandwidth is the root cause.",
    ],
    "network.path": [
        "Use to compare the hop path, loss, and delay for one suspected node pair. Prefer overlay and underlay comparisons when isolating the failing plane.",
        "Missing intermediate hop replies do not prove that the path is broken; routers may suppress ICMP responses.",
    ],
    "network.dns": [
        "Use only for Kubernetes service names under svc.cluster.local when DNS latency or resolution failure is a credible hypothesis.",
        "Compare results from affected and healthy worker probes when possible.",
    ],
    "network.tcp_connect": [
        "Use to validate reachability and connection time to one declared Kubernetes Service port from a selected worker.",
        "A successful TCP connection does not prove application health; correlate it with service endpoints, request metrics, logs, or traces.",
    ],
    "cluster.profile_baseline": [
        "Use as the orchestrator's first investigation call, before spawning targeted investigation agents.",
        "It inventories every current Deployment in the selected namespace and every cluster node, then joins Kubernetes state with bounded Prometheus metrics, Loki error samples, passive network-probe coverage, and an active directed latency matrix between Ready service workers.",
        "When a detector timestamp is available, pass it as `evaluation_time`; otherwise use the default recent 30-minute window.",
        "Inspect `coverage.missing_signals`, `errors`, and each resource's `missing_signals`. Empty or failed signals are missing evidence, never proof of health.",
        "The latency matrix uses ten ICMP samples per directed worker pair over both overlay and underlay paths; the tool performs no active path, DNS, TCP-connect, or bandwidth probes and makes no cluster mutations.",
    ],
    "agent_spawner": [
        "Use only from the orchestrator to delegate bounded evidence gathering to sub-agents.",
        "Never include `agent_spawner` in a spawned sub-agent's tools.",
        "Give each spawned agent a focused task, bounded tools, evidence standards, and `max_rounds`.",
        "Use `max_rounds=10` normally, `5` for a simple focused check, and a higher value up to `20` for a difficult investigation that needs multiple correlated signals.",
    ],
}


def build_tool_usage_context(
    names: list[str],
    descriptions: dict[str, str],
) -> str:
    selected = []
    seen = set()
    for name in names:
        if name in seen or name not in descriptions:
            continue
        seen.add(name)
        selected.append(name)

    if not selected:
        return ""

    sections = [
        "# Available Tool Operating Guide",
        "",
        "You only have the tools listed below. Use them according to this guide, "
        "and do not attempt to call tools that are not available to you.",
        "Use the exact tool names shown as section headers. Do not create method-style tool names such as `prometheus.query`, `prometheus.query_range`, `loki.query`, or `loki.query_range`; use `prometheus` or `loki` with the `query_type` argument instead.",
    ]

    for name in selected:
        sections.extend(["", f"## {name}", "", f"- Description: {descriptions[name]}"])
        for item in TOOL_USAGE_CONTEXT.get(name, []):
            sections.append(f"- {item}")
        if name == "prometheus":
            sections.extend(["", "### Prometheus Metric Reference"])
            for signal_name, metric_names in DETECTOR_METRIC_REFERENCE.items():
                metrics = ", ".join(f"`{metric_name}`" for metric_name in metric_names)
                sections.append(f"- `{signal_name}`: use {metrics}")

    return "\n".join(sections)
