# sock-shop-pod-catalogue-cpu-all-ten-minutes

## RCA

### Expected incident condition

- Every Running `catalogue` replica experiences a recurring increase in CPU usage leading to saturation, creating service-wide compute contention rather than a single-node, database, memory, or version issue.
- The affected pods have a 200m CPU limit, so sustained demand exhausts their available compute while memory remains healthy.
- `catalogue` serves product listings and product details used by the storefront. Degradation affects `/catalogue`, category browsing, product detail, and cart selection that needs a valid product.

### Expected diagnosis and evidence

- **Root cause:** recurring service-wide CPU saturation affects all `catalogue` replicas in namespace `sock-shop`.
- **Corroboration:** CPU usage rises to saturation across all `catalogue` replicas without a single-node concentration; restarts, OOM kills, node pressure, `catalogue-db`, and unrelated services remain comparatively healthy.
- A full RCA identifies the workload, namespace, CPU dimension, all-replica scope, recurrence, and impact on the product-browsing path. A front-end timeout alone is a symptom, not a complete localization.

## Recommended remediation

### Fully correct

- Increase only `catalogue` CPU capacity using current measurements: vertically raise its CPU request and limit within eligible-node capacity, or apply conservative bounded horizontal scaling using its existing HPA. Preserve `catalogue-db` and all unrelated workload settings.
- Keep replica growth bounded by the established maximum, confirm every new pod schedules, and avoid pairing aggressive scale-out with oversized per-pod requests.

### Helpful but incomplete

- A conservative temporary replica increase or a single measured CPU adjustment can reduce pressure, but is incomplete without durable bounds, coherent request/limit sizing, rollout validation, and user-path verification.

### Rejected approaches

- Restart-only treatment is transient because replacement pods experience the same unresolved service-wide CPU pressure. Node isolation, database mutation, memory increases, and unrelated-service changes do not address pressure affecting every replica.
- Version rollback without version-related evidence, disabling outbound or dependency calls, bypassing catalogue traffic, scaling traffic or a workload to zero, and destructive cluster or application changes are rejected because they do not address the diagnosed condition or introduce unacceptable risk.

### Verification

- Verify the applied `catalogue` spec and HPA bounds, rollout, desired versus Ready replicas, pod scheduling, CPU response, absence of OOM kills and node pressure, and recovery of catalogue plus end-to-end shopping requests. Confirm response-time P95 and HTTP 5xx rate over the recovery window rather than inferring success from a mutation command.
