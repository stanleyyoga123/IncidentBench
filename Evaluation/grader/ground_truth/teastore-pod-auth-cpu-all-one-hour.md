# teastore-pod-auth-cpu-all-one-hour

## RCA

### Expected incident condition

- Every Running `teastore-auth` replica experiences a recurring increase in CPU usage leading to saturation, creating service-wide compute contention rather than a single-node or version issue.
- `teastore-auth` handles TeaStore login and authentication; degradation blocks authenticated user journeys while unrelated static paths may remain available.

### Expected diagnosis and evidence

- **Root cause:** Recurring service-wide CPU saturation affects all `teastore-auth` replicas in namespace `teastore`.
- **Corroboration:** CPU usage must rise to saturation across all `teastore-auth` replicas without a single-node concentration; node memory and unrelated workloads should remain comparatively healthy.
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Increase only `teastore-auth` CPU capacity using measured evidence: either vertically raise request and limit within eligible-node capacity, or use bounded horizontal scaling with an explicit capacity-tested HPA maximum. Do not combine aggressive replica growth with oversized requests.

### Helpful but incomplete

- A conservative one-dimensional CPU change or bounded temporary scale-out can reduce pressure and earns partial credit when it is safe, but it is incomplete without coherent sizing, bounds, and rollout verification.

### Rejected approaches

- Restart-only treatment is transient because replacement pods experience the same unresolved service-wide CPU pressure. Node isolation and unrelated-service mutations do not address pressure affecting every replica.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
