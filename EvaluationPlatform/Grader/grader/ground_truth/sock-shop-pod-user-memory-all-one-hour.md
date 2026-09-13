# sock-shop-pod-user-memory-all-one-hour

## RCA

### Expected incident condition

- Every Running `user` replica experiences recurring per-pod memory pressure, exhausting container memory headroom rather than causing node-wide memory exhaustion.
- `user` provides registration, authentication, customer addresses and cards backed by `user-db`; verify login and customer data used during checkout.

### Expected diagnosis and evidence

- **Root cause:** Recurring per-pod memory pressure affects all `user` replicas in namespace `sock-shop`.
- **Corroboration:** Working-set and limit utilization, OOM/restart evidence, and memory pressure must affect all `user` pods while nodes and unrelated services retain memory headroom.
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Vertically right-size only `user` memory request and limit using working-set, OOM, and eligible-node-capacity evidence. Preserve CPU and unrelated settings and complete a controlled rollout.

### Helpful but incomplete

- A safe limit-only increase or one controlled restart after memory pressure has cleared can restore service and earns partial credit, but request/QoS or recurring headroom remains unresolved.

### Rejected approaches

- Horizontal scaling does not remove per-pod memory pressure affecting every replica. Repeated restart-only treatment while memory pressure persists, node isolation, or oversized unschedulable memory values are not safe fixes.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
