# teastore-pod-auth-cpu-all-one-hour

## RCA

- **Incident pattern:** Login and session operations become slow or fail even though unrelated TeaStore paths remain comparatively healthy.
- **Affected scope:** All running `teastore-auth` replicas are CPU constrained, so load balancing cannot route requests to an unaffected instance.
- **Root cause:** An abnormal CPU-intensive execution path or runaway process in `teastore-auth` is consuming its available CPU and causing sustained service CPU saturation.
- **Corroborating evidence:** High CPU usage or throttling across every `teastore-auth` pod, increased latency or errors on that service, and no single-node concentration support a service-wide CPU problem rather than an HPA, dependency, or cluster-network issue.

## Recommended remediation

- Prefer vertical scaling when the existing replicas can safely handle the workload: increase `teastore-auth` CPU requests and limits using measured usage, throttling, and available node capacity as the sizing basis.
- Alternatively, use horizontal scaling with an explicit, capacity-tested HPA maximum so `teastore-auth` gains enough replicas to recover without growing to an excessive instance count or exhausting cluster capacity.
- Apply either scaling change as a controlled rollout that preserves availability, and do not combine an aggressive replica target with oversized per-pod resource requests.
- Verify that CPU usage and throttling fall across `teastore-auth` and that latency, errors, traffic, endpoint health, and downstream request completion recover.
