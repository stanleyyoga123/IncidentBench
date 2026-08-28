# real-pod-cartservice-cpu-all-one-hour

## RCA

- **Incident pattern:** Cart operations become slow or fail even though
  unrelated storefront paths remain comparatively healthy.
- **Affected scope:** All running `cartservice` replicas are CPU constrained, so
  load balancing cannot route requests to an unaffected instance.
- **Root cause:** An abnormal CPU-intensive execution path or runaway process in
  `cartservice` is consuming its available CPU and causing sustained service
  CPU saturation.
- **Corroborating evidence:** High CPU usage or throttling across every
  `cartservice` pod, increased cart RPC latency or errors, and no single-node
  concentration support a service-wide CPU problem rather than an HPA,
  dependency, or cluster-network issue.

## Recommended remediation

- Prefer vertical scaling when the existing replicas can safely handle the
  workload: increase `cartservice` CPU requests and limits using measured usage,
  throttling, and available node capacity as the sizing basis.
- Alternatively, use horizontal scaling with an explicit, capacity-tested HPA
  maximum so `cartservice` gains enough replicas to recover without growing to
  an excessive instance count or exhausting cluster capacity.
- Apply either scaling change as a controlled rollout that preserves cart
  availability, and do not combine an aggressive replica target with oversized
  per-pod resource requests.
- Verify that CPU usage and throttling fall across `cartservice` and that cart
  latency, errors, traffic, endpoint health, and downstream request completion
  recover.
