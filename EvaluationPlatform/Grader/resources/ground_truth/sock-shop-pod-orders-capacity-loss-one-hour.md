# sock-shop-pod-orders-capacity-loss-one-hour

## RCA

### Expected incident condition

- One Running `orders` pod repeatedly becomes unavailable, reducing the service's healthy endpoint capacity and exposing its single-replica-loss tolerance.
- `orders` coordinates checkout across customer records, cart, payment and shipping, with order state stored in `orders-db`; verify order creation and downstream completion.

### Expected diagnosis and evidence

- **Root cause:** Recurring loss of one `orders` endpoint at a time in namespace `sock-shop`, combined with insufficient durable N+1 capacity.
- **Corroboration:** One `orders` endpoint repeatedly becomes unavailable while survivors stay healthy but carry concentrated traffic; the impact should match the target's role (coordinates customer records, carts, payment and shipping; degradation can block transaction completion).
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Create durable N+1 capacity for `orders` with one bounded HPA patch: raise `minReplicas` so at least two healthy endpoints remain during one loss and retain or set a capacity-tested `maxReplicas`.

### Helpful but incomplete

- A safe direct replica increase can temporarily improve availability and earns partial credit, but the HPA may reconcile it; raising only the minimum can also help when the existing maximum is explicitly validated as safe.

### Rejected approaches

- Restarting the repeatedly failed pod does not add failure tolerance. Unbounded scaling, node isolation without node evidence, or unrelated resource changes are not safe capacity remediation.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
