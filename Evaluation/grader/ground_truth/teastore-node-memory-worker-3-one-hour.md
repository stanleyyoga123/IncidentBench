# teastore-node-memory-worker-3-one-hour

## RCA

- **Incident pattern:** Several unrelated workloads on `worker-node-3` slow,
  are evicted, or become unavailable as the node approaches memory exhaustion.
- **Affected scope:** The impact follows node placement and can affect every pod
  sharing the host rather than one service or workload definition.
- **Root cause:** `worker-node-3` is under sustained host memory pressure,
  consistent with a leaking process, oversized cache, runaway allocation, or
  noisy-neighbour workload consuming most available memory.
- **Corroborating evidence:** High node memory utilization, low available memory,
  eviction or OOM evidence, and correlated degradation among colocated pods
  support a node-level memory problem.

## Recommended remediation

- Cordon `worker-node-3` to prevent additional memory demand from being placed
  on the affected host.
- Safely drain evictable workloads to healthy nodes with sufficient memory while
  respecting disruption budgets and local-data constraints.
- Keep the node unschedulable until the leaking or over-consuming process is
  stopped and memory headroom remains stable under observation.
- Verify available node memory, absence of new OOM kills or evictions, replacement
  pod readiness, application latency, traffic, and errors before returning the
  node to service.
