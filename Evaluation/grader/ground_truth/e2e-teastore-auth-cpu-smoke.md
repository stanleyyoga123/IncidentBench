# e2e-teastore-auth-cpu-smoke

## RCA

### Authoritative fault

- StressChaos adds one 55% CPU worker to every Running `teastore-auth` replica for 25s in every 30s cycle, creating service-wide CPU contention rather than a single-node or version fault.
- `teastore-auth` handles TeaStore login and authentication; degradation blocks authenticated user journeys while unrelated static paths may remain available.

### Expected diagnosis and evidence

- **Root cause:** The injected `StressChaos` condition is scoped to every selected `teastore-auth` pod in namespace `teastore`.
- **Corroboration:** CPU usage and throttling must rise across all `teastore-auth` replicas without a single-node concentration; node memory and unrelated workloads should remain comparatively healthy.
- A full RCA must name the correct workload, fault dimension, selector scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Increase only `teastore-auth` CPU capacity using measured evidence: either vertically raise request and limit within eligible-node capacity, or use bounded horizontal scaling with an explicit capacity-tested HPA maximum. Do not combine aggressive replica growth with oversized requests.

### Helpful but incomplete

- A conservative one-dimensional CPU change or bounded temporary scale-out can reduce pressure and earns partial credit when it is safe, but it is incomplete without coherent sizing, bounds, and rollout verification.

### Rejected approaches

- Restart-only treatment is transient because the recurring stress targets replacement pods. Node isolation and unrelated-service mutations do not address a service-wide selector.
- Version rollback, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, or deleting or modifying the Chaos Mesh Schedule/injected host state are not accepted simulation remediations.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, target-specific fault evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
