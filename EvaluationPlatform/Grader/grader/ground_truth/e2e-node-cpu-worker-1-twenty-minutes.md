# e2e-node-cpu-worker-1-twenty-minutes

## RCA

### Authoritative fault

- PhysicalMachineChaos runs 8 CPU stress workers at 90% load on `worker-node-1`, active for 25s in every 30s cycle. This is a shortened smoke run, but the expected diagnosis is unchanged.
- The affected scope is the node and every application workload whose request path or placement depends on it, not one Deployment.

### Expected diagnosis and evidence

- **Root cause:** A recurring node-level `stress-cpu` condition on `worker-node-1` caused by the injected PhysicalMachineChaos.
- **Incident pattern:** Unrelated workloads placed on `worker-node-1` contend for host CPU and can become slow or throttled while replicas on other nodes remain healthier.
- **Corroboration:** Sustained node CPU saturation on `worker-node-1`, scheduling delay or throttling across colocated pods, and the absence of one service-wide hotspot establish a node fault.
- Identifying only a degraded application is incomplete. A full RCA must localize the shared failure boundary to `worker-node-1` and distinguish `stress-cpu` from service CPU, memory, HPA, or version problems.

## Recommended remediation

### Fully correct

- Validate `worker-node-1`, replacement capacity, resident workloads, PodDisruptionBudgets, local-data impact, and control-plane risk; then cordon `worker-node-1` and safely drain evictable workloads with a bounded timeout, `--ignore-daemonsets`, and `--delete-emptydir-data`, without `--force` or disabled eviction.
- Keep `worker-node-1` unschedulable while the injected condition remains. Uncordon only after the fault has ended and current node plus application evidence demonstrates stable recovery.

### Helpful but incomplete

- Cordon without completing a safe drain prevents new exposure but leaves existing workloads affected.
- A bounded pod-template relocation of one confirmed affected Deployment away from `worker-node-1` can improve that service but does not protect other workloads or isolate the node-wide fault.
- A restart that happens to move a pod may provide transient relief, but it is uncontrolled and is not a durable node remediation.

### Rejected approaches

- Scaling or changing resources of an application does not remove the node-wide fault. Draining another node, prematurely uncordoning `worker-node-1`, force-draining through disruption safeguards, or repeatedly restarting workloads can increase harm.
- Version rollback, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, or deleting or modifying the Chaos Mesh Schedule/injected host state are not accepted simulation remediations.

### Verification

- Verify `worker-node-1` schedulability and fault-specific node evidence, absence of evictable application pods on it, replacement pod readiness, and recovery of response-time P95 and HTTP 5xx rate. Preserve the node isolation if recovery is ambiguous.
