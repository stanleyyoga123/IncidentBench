# real-pod-recommendationservice-cpu-all-one-hour

## RCA

- **Incident pattern:** Recommendation requests become slow or fail, degrading
  recommendation panels and any frontend path that waits for those responses
  while core catalog retrieval may remain available.
- **Affected scope:** All running `recommendationservice` replicas are CPU
  constrained, so load balancing cannot select a healthy recommendation
  instance.
- **Root cause:** An abnormal CPU-intensive execution path or runaway process in
  `recommendationservice` is consuming its available CPU and causing sustained
  service CPU saturation.
- **Corroborating evidence:** High CPU usage or throttling across every
  recommendation pod, elevated recommendation RPC latency or errors, and healthy
  catalog behavior outside that call path support a service-wide CPU problem
  rather than a cluster-wide resource shortage.

## Recommended remediation

- Prefer vertical scaling when the existing replicas can safely handle the
  workload: increase `recommendationservice` CPU requests and limits using
  measured usage, throttling, and available node capacity as the sizing basis.
- Alternatively, use horizontal scaling with an explicit, capacity-tested HPA
  maximum so `recommendationservice` gains enough replicas to recover without
  growing to an excessive instance count or exhausting cluster capacity.
- Apply either scaling change as a controlled rollout that preserves frontend
  availability, allowing graceful degradation of recommendations where
  supported.
- Verify that CPU usage and throttling fall across `recommendationservice` and
  that recommendation latency, errors, traffic, endpoint health, and frontend
  request completion recover.
