# online-boutique-pod-shippingservice-bandwidth-all-one-hour

## RCA

### Expected incident condition

- Every Running `shippingservice` pod exhibits an approximately 1 Mbps throughput ceiling. The constraint is per pod, so aggregate service bandwidth—not CPU, memory, or a node link—is the limiting resource.
- `shippingservice` provides shipping quotes and order-shipping data used by checkout.

### Expected diagnosis and evidence

- **Root cause:** A recurring per-pod network throughput constraint affects all `shippingservice` replicas in namespace `online-boutique`.
- **Corroboration:** Per-pod throughput should plateau across `shippingservice` replicas while CPU, memory, readiness, dependencies, and node links remain healthy; queueing, latency, or errors should follow traffic demand.
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Increase aggregate `shippingservice` throughput with one bounded HPA patch: raise `minReplicas` based on demand and set an explicit capacity-tested `maxReplicas`, while preserving resources and service behavior.

### Helpful but incomplete

- A safe direct replica increase can temporarily add per-pod bandwidth and earns partial credit, but an existing HPA may reconcile it unless durable bounds are updated.

### Rejected approaches

- CPU or memory sizing, node isolation, restart-only treatment, or unbounded scale-out does not safely address the per-pod network ceiling.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
