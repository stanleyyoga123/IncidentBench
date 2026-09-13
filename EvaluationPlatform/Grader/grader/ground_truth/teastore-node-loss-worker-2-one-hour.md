# teastore-node-loss-worker-2-one-hour

## RCA

### Expected incident condition

- `worker-node-2` has recurring packet loss of approximately 20% on `eth0`, causing intermittent failures on paths to and from workloads on that node.
- The affected scope is the node and every application workload whose request path or placement depends on it, not one Deployment.

### Expected diagnosis and evidence

- **Root cause:** Recurring node-level packet loss on `worker-node-2` degrades every request path that crosses that node.
- **Incident pattern:** RPCs involving pods on `worker-node-2` fail intermittently or time out, affecting multiple otherwise unrelated services whenever a request path crosses that host.
- **Corroboration:** Failed probes, retransmission-like behavior, endpoint errors, and a failure pattern correlated with `worker-node-2` distinguish packet loss from uniform processing delay or an application-only defect.
- Identifying only a degraded application is incomplete. A full RCA must localize the shared failure boundary to `worker-node-2` and distinguish node-level packet loss from service CPU, memory, HPA, or version problems.

## Recommended remediation

### Fully correct

- Validate `worker-node-2`, replacement capacity, resident workloads, PodDisruptionBudgets, local-data impact, and control-plane risk; then cordon `worker-node-2` and safely drain evictable workloads with a bounded timeout, `--ignore-daemonsets`, and `--delete-emptydir-data`, without `--force` or disabled eviction.
- Keep `worker-node-2` unschedulable while current evidence shows that it remains impaired. Uncordon only after current node and application evidence demonstrates stable recovery.

### Helpful but incomplete

- Cordon without completing a safe drain prevents new exposure but leaves existing workloads affected.
- A bounded pod-template relocation of one confirmed affected Deployment away from `worker-node-2` can improve that service but does not protect other workloads or isolate the node-wide fault.
- A restart that happens to move a pod may provide transient relief, but it is uncontrolled and is not a durable node remediation.

### Rejected approaches

- Scaling or changing resources of an application does not remove the node-wide fault. Draining another node, prematurely uncordoning `worker-node-2`, force-draining through disruption safeguards, or repeatedly restarting workloads can increase harm.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify `worker-node-2` schedulability and condition-specific node evidence, absence of evictable application pods on it, replacement pod readiness, and recovery of response-time P95 and HTTP 5xx rate. Preserve the node isolation if recovery is ambiguous.
