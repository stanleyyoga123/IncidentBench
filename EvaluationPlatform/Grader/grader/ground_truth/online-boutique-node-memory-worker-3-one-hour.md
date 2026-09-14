# online-boutique-node-memory-worker-3-one-hour

## RCA

### Expected incident condition

- `worker-node-3` has recurring node-level memory pressure that collapses host memory headroom for every workload placed on it.
- The affected scope is the node and every application workload whose request path or placement depends on it, not one Deployment.

### Expected diagnosis and evidence

- **Root cause:** Recurring memory pressure on `worker-node-3` creates host-level contention and eviction or OOM risk across colocated workloads.
- **Incident pattern:** Unrelated workloads on `worker-node-3` can slow, be evicted, or become unavailable as host memory headroom collapses.
- **Corroboration:** Low available memory and MemoryPressure, eviction, or OOM evidence on `worker-node-3`, correlated across colocated services, distinguish node pressure from one container's sizing problem.
- Identifying only a degraded application is incomplete. A full RCA must localize the shared failure boundary to `worker-node-3` and distinguish node-level memory pressure from a single container sizing problem, CPU, HPA, or version issues.

## Recommended remediation

### Fully correct

- Validate `worker-node-3`, replacement capacity, resident workloads, PodDisruptionBudgets, local-data impact, and control-plane risk; then cordon `worker-node-3` and safely drain evictable workloads with a bounded timeout, `--ignore-daemonsets`, and `--delete-emptydir-data`, without `--force` or disabled eviction.
- Keep `worker-node-3` unschedulable while current evidence shows that it remains impaired. Uncordon only after current node and application evidence demonstrates stable recovery.

### Helpful but incomplete

- Cordon without completing a safe drain prevents new exposure but leaves existing workloads affected.
- A bounded pod-template relocation of one confirmed affected Deployment away from `worker-node-3` can improve that service but does not protect other workloads or isolate the node-wide fault.
- A restart that happens to move a pod may provide transient relief, but it is uncontrolled and is not a durable node remediation.

### Rejected approaches

- Scaling or changing resources of an application does not remove the node-wide fault. Draining another node, prematurely uncordoning `worker-node-3`, force-draining through disruption safeguards, or repeatedly restarting workloads can increase harm.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify `worker-node-3` schedulability and condition-specific node evidence, absence of evictable application pods on it, replacement pod readiness, and recovery of response-time P95 and HTTP 5xx rate. Preserve the node isolation if recovery is ambiguous.
