CLUSTER_KNOWLEDGE = """# Kubernetes SRE Cluster Knowledge

Use this as lightweight baseline context. Treat it as a starting point, not proof.
Re-check live Kubernetes state, metrics, logs, and traces during each incident.

## Cluster Context

- Kubernetes distribution: k3s.
- One or more microservice applications may be active. Their namespaces are
  supplied at runtime and must be preserved throughout investigation and
  remediation planning.
- Application names, entry points, service dependencies, replica policies, and
  sidecar presence are workload-specific and must be discovered live.
- Prometheus is in `monitoring`, Loki is in `observability`, and Jaeger/Istio components are in `istio-system`.
- Supporting namespaces include `agents`, `loadgenerator`, and `utility`.

## Expected Node Topology

- `master-node-1` is the control-plane node.
- `tools-node` and `misc-node-1` are tooling nodes and normally use `role=tools`.
- `worker-node-1` through `worker-node-6` are application-capable worker nodes. Most normally use `role=services`, but labels may not be uniform; verify them live.
- Application workloads normally run on worker nodes, while agent and observability workloads normally run on tooling nodes.

## Application Topology

- Discover Deployments, StatefulSets, Services, endpoints, HPAs, ingress or
  gateway entry points, sidecars, and dependency paths in the incident's
  namespace. Do not import topology from another application.
- Treat a user-visible entry service as a symptom source, not the default root
  cause.
- Re-check autoscaling targets, replica bounds, resource policies, and behavior
  live before recommending changes.

## Application Invariants

- Application versions are normally stable in this testbed. Treat a version regression as low probability unless live evidence contradicts this.
- Deployments do not maintain meaningful version history for recovery. `kubectl rollout undo` is not expected to change application behavior and should not be recommended as remediation.
- Under normal load and healthy infrastructure, the application is expected to operate correctly.
- For performance degradation, prioritize runtime causes such as node CPU or memory pressure, network throughput or latency, disk pressure, pod placement, uneven load, resource throttling, scaling delay, traffic bursts, and dependency saturation.
- A node- or pod-level bandwidth constraint may appear as sustained demand with a throughput ceiling, rising latency or timeouts, retransmits or drops, and affected pods sharing a node or network path. The physical node interface does not need to be fully utilized.
- These are investigation priors, not proof. Confirm the cause with current Kubernetes state and correlated metrics, logs, or traces.

## Investigation Defaults

- There is no default application namespace or user-visible service. Use the
  runtime workload scope and live discovery.
- If no time window is provided, inspect recent data.
- Treat this knowledge as expected topology, not current health. Verify nodes, deployments, replicas, HPAs, PodDisruptionBudgets, endpoints, and placement live.
- Empty metrics, logs, or traces are not proof of health. Treat them as missing evidence or a tool/data gap.

## Evidence Standards

- Preserve exact service names, namespaces, pod names, node names, timestamps, counts, errors, and tool failures.
- Separate evidence from assumptions.
"""
