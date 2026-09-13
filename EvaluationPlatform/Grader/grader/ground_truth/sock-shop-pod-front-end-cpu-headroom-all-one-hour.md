# sock-shop-pod-front-end-cpu-headroom-all-one-hour

## RCA

### Expected incident condition

- The `front-end` Deployment configures CPU request and limit both `100m`. Recurring CPU demand reaches this hard limit, leaving no burst headroom and driving CPU saturation across the workload.
- `front-end` serves the storefront and coordinates browser requests with backend services and session storage; verify the complete user journey.

### Expected diagnosis and evidence

- **Root cause:** Insufficient per-pod CPU headroom on `front-end` in namespace `sock-shop`: request and limit are both `100m`, so demand cannot burst above the requested CPU.
- **Corroboration:** CPU usage must rise to saturation across all `front-end` replicas without a single-node concentration; node memory and unrelated workloads should remain comparatively healthy.
- A full RCA must name the correct workload, resource or failure dimension, affected scope, and operational effect. Naming only an upstream symptom or dependent service is partial localization.

## Recommended remediation

### Fully correct

- Vertically right-size only `front-end` in namespace `sock-shop`. Increase both CPU request and limit from `100m` using observed sustained demand and eligible-node capacity, keep `request < limit`, preserve memory and unrelated settings, and complete a controlled rollout.

### Helpful but incomplete

- A safe limit-only increase can add CPU headroom and reduce saturation and earns partial credit, but leaves the request and CPU-HPA utilization denominator mis-sized. A bounded temporary replica increase can add capacity but does not correct per-pod headroom.

### Rejected approaches

- A request-only increase without usable limit headroom, request greater than or equal to limit, unschedulable sizing, unbounded scale-out, or restart-only treatment does not safely correct the policy.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied spec and rollout, desired versus Ready replicas, schedulability and capacity, condition-specific evidence, dependent-path health, and recovery of response-time P95 and HTTP 5xx rate. Do not infer recovery from a successful mutation command alone.
