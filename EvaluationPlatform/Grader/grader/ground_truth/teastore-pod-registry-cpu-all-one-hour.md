# teastore-pod-registry-cpu-all-one-hour

## RCA

### Expected incident condition

- Every Running `teastore-registry` replica experiences a recurring increase in CPU usage leading to saturation, creating service-wide compute contention rather than a single-node or version issue.
- `teastore-registry` is TeaStore's singleton in-memory service registry; extra replicas do not share registrations and can split discovery state.

### Expected diagnosis and evidence

- **Root cause:** Recurring service-wide CPU saturation affects all `teastore-registry` replicas in namespace `teastore`.
- **Corroboration:** CPU usage must rise to saturation across all `teastore-registry` replicas without a single-node concentration; node memory and unrelated workloads should remain comparatively healthy.
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Vertically increase only `teastore-registry` CPU request and limit using measured CPU usage, saturation, and node headroom. Preserve its single replica because independent registry replicas split in-memory registrations.

### Helpful but incomplete

- A conservative limit-only increase can add CPU headroom and reduce saturation but is incomplete if the request remains inconsistent with sustained demand.

### Rejected approaches

- Adding registry replicas or an HPA is state-invalid. Repeated restart-only treatment is transient because the replacement pod experiences the same unresolved CPU pressure.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
