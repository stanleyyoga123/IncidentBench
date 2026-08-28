# real-pod-productcatalogservice-cpu-headroom-all-one-hour

## RCA

- **Incident pattern:** Product listing, search, and product-detail requests slow
  during sustained catalog demand while node capacity and service dependencies
  remain healthy.
- **Affected scope:** Every `productcatalogservice` replica is governed by the
  same CPU policy, so traffic cannot reach an instance with burst headroom.
- **Root cause:** `productcatalogservice` has an overly restrictive CPU
  configuration: its `250m` limit equals its `250m` request despite legitimate
  catalog processing demand above that allocation.
- **Operational effect:** CPU throttling increases catalog RPC duration and
  CPU-utilization HPA demand; replicas remain individually constrained even as
  the HPA attempts to add capacity.
- **Corroborating evidence:** Equal request and limit in the Deployment, CPU
  plateauing near `250m`, throttling across all catalog pods, healthy node CPU,
  and catalog-specific latency localize the configuration defect.

## Recommended remediation

- Vertically right-size only `productcatalogservice` with `kubectl set resources
  deployment/productcatalogservice -n online-boutique --containers=server`,
  increasing both its CPU request and limit from the constrained values.
- Choose the request from measured sustained demand and the HPA's 70% target,
  then retain a higher limit for legitimate bursts. The resulting configuration
  must have `request < limit` and fit eligible-node capacity.
- Preserve memory settings and avoid changing frontend, recommendation, or
  checkout resources without independent evidence against those services.
- Verify the applied resources, schedulability, ready replicas, lower throttling,
  stable bounded HPA demand, catalog latency and errors, healthy endpoints, and
  successful product retrieval.
