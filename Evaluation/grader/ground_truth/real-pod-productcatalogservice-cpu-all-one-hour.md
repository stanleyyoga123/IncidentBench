# real-pod-productcatalogservice-cpu-all-one-hour

## RCA

- **Incident pattern:** Product listing, search, and product-detail requests
  become slow or fail, with secondary impact on services that require catalog
  data.
- **Affected scope:** All running `productcatalogservice` replicas are CPU
  constrained, leaving no healthy catalog endpoint for frontend and downstream
  callers.
- **Root cause:** An abnormal CPU-intensive execution path or runaway process in
  `productcatalogservice` is consuming its available CPU and causing sustained
  service CPU saturation.
- **Corroborating evidence:** High CPU usage or throttling across every catalog
  pod, elevated catalog RPC latency or errors, and failures in catalog-dependent
  paths support a service-wide CPU problem rather than a single node, HPA, or
  network issue.

## Recommended remediation

- Prefer vertical scaling when the existing replicas can safely handle the
  workload: increase `productcatalogservice` CPU requests and limits using
  measured usage, throttling, and available node capacity as the sizing basis.
- Alternatively, use horizontal scaling with an explicit, capacity-tested HPA
  maximum so `productcatalogservice` gains enough replicas to recover without
  growing to an excessive instance count or exhausting cluster capacity.
- Apply either scaling change as a controlled rollout that preserves catalog
  availability, and confirm that frontend and recommendation callers can
  retrieve catalog data.
- Verify that CPU usage and throttling fall across `productcatalogservice` and
  that catalog latency, errors, traffic, endpoint health, search, and product
  retrieval recover.
