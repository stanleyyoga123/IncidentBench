# teastore-pod-registry-capacity-loss-one-hour

## RCA

### Expected incident condition

- One Running `teastore-registry` pod repeatedly becomes unavailable, reducing the service's healthy endpoint capacity and exposing its single-replica-loss tolerance.
- `teastore-registry` is TeaStore's singleton in-memory service registry; extra replicas do not share registrations and can split discovery state.

### Expected diagnosis and evidence

- **Root cause:** Recurring loss of the only `teastore-registry` endpoint in namespace `teastore` interrupts service discovery; its independent in-memory catalog prevents safe horizontal replication.
- **Corroboration:** The only registry endpoint repeatedly disappears, service heartbeats/lookups fail, and no second shared catalog exists; other resources and nodes remain healthy.
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- While registry endpoint instability continues, preserve the singleton and avoid unsafe mutation. After current pod and endpoint evidence demonstrates stability, ensure the existing Deployment restores exactly one Ready registry pod; recreate that one pod only if it remains stuck, then verify registrations and heartbeats have repopulated.

### Helpful but incomplete

- A carefully validated single-pod recreation after endpoint stability returns can restore discovery and earns credit even if broader recovery verification is incomplete. While instability continues, a validation-only response is safer than futile churn.

### Rejected approaches

- Do not add replicas or an HPA: independent in-memory catalogs split registrations. Restarting repeatedly while endpoint instability continues only recreates an endpoint exposed to the same unresolved condition.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
