# e2e-online-boutique-cartservice-cpu-smoke

## RCA

### Authoritative fault

- StressChaos adds one 55% CPU worker to every Running `cartservice` replica for 25s in every 30s cycle, creating service-wide CPU contention rather than a single-node or version fault.
- `cartservice` owns cart reads and writes and depends on Redis; degradation affects cart operations and checkout's cart lookup.

### Expected diagnosis and evidence

- **Root cause:** The injected `StressChaos` condition is scoped to every selected `cartservice` pod in namespace `online-boutique`.
- **Corroboration:** CPU usage and throttling must rise across all `cartservice` replicas without a single-node concentration; node memory and unrelated workloads should remain comparatively healthy.
- A full RCA must name the correct workload, fault dimension, selector scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Increase only `cartservice` CPU capacity using measured evidence: either vertically raise request and limit within eligible-node capacity, or use bounded horizontal scaling with an explicit capacity-tested HPA maximum. Do not combine aggressive replica growth with oversized requests.

### Helpful but incomplete

- A conservative one-dimensional CPU change or bounded temporary scale-out can reduce pressure and earns partial credit when it is safe, but it is incomplete without coherent sizing, bounds, and rollout verification.

### Rejected approaches

- Restart-only treatment is transient because the recurring stress targets replacement pods. Node isolation and unrelated-service mutations do not address a service-wide selector.
- Version rollback, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, or deleting or modifying the Chaos Mesh Schedule/injected host state are not accepted simulation remediations.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, target-specific fault evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
