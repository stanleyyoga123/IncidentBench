# real-pod-productcatalogservice-bandwidth-all-one-hour

## RCA

- **Incident pattern:** Product listing, search, and product-detail responses
  slow down as traffic grows, although CPU, memory, pod readiness, and dependency
  health remain normal.
- **Affected scope:** Every `productcatalogservice` replica reaches a per-instance
  network throughput ceiling, constraining aggregate catalog throughput.
- **Root cause:** `productcatalogservice` has insufficient horizontal capacity
  for a per-pod bandwidth bottleneck, consistent with a sidecar, CNI, interface,
  or platform rate limit applied independently to each instance.
- **Corroborating evidence:** Per-pod network throughput plateaus, request queues
  and latency grow with traffic, CPU remains below saturation, and load is evenly
  distributed across otherwise healthy catalog pods.

## Recommended remediation

- Increase aggregate service throughput with `kubectl patch hpa
  productcatalogservice-hpa -n online-boutique`, raising `minReplicas` so traffic
  is distributed across more independently limited pods.
- Set a justified `maxReplicas` in the same HPA change to prevent runaway
  instance growth and keep total requested capacity within cluster limits.
- Do not vertically increase CPU or memory when evidence identifies network
  throughput—not compute or memory—as the limiting resource.
- Verify the HPA bounds, desired and ready replicas, lower traffic per pod,
  improved aggregate traffic, catalog latency and errors, endpoint health, and
  product retrieval.
