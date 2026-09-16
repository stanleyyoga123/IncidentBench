# sock-shop-node-cpu-worker-2-one-hour

## RCA

### Expected incident condition

- `worker-node-2` has recurring node-level CPU saturation that reduces compute headroom for every workload placed on it.
- The affected scope is the node and every application workload whose request path or placement depends on it, not one Deployment.

### Expected diagnosis and evidence

- **Root cause:** Recurring CPU saturation on `worker-node-2` creates host-level contention across otherwise unrelated colocated workloads.
- **Incident pattern:** Unrelated workloads placed on `worker-node-2` contend for host CPU and can become slow under CPU saturation while replicas on other nodes remain healthier.
- **Corroboration:** Sustained node CPU saturation on `worker-node-2`, scheduling delay or reduced CPU headroom across colocated pods, and the absence of one service-wide hotspot establish a node fault.
- Identifying only a degraded application is incomplete. A full RCA must localize the shared failure boundary to `worker-node-2` and distinguish node-level CPU saturation from service CPU, memory, HPA, or version problems.

## Recommended remediation

### Fully correct

- Validate `worker-node-2`, replacement capacity, resident workloads, PodDisruptionBudgets, local-data impact, and control-plane risk; then cordon `worker-node-2` and safely drain evictable workloads with a bounded timeout while respecting disruption and storage constraints. Sock Shop databases use local ephemeral volumes: do not delete those volumes or evict a database pod until a data-preserving recovery path has been established. Do not use forced eviction or blindly permit deletion of local data.
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
