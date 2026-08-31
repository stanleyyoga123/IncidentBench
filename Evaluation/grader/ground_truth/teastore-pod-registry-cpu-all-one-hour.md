# teastore-pod-registry-cpu-all-one-hour

## RCA

- **Incident pattern:** Service discovery and registry lookups become slow or fail even though unrelated TeaStore paths remain comparatively healthy.
- **Affected scope:** All running `teastore-registry` replicas are CPU constrained, so load balancing cannot route requests to an unaffected instance.
- **Root cause:** An abnormal CPU-intensive execution path or runaway process in `teastore-registry` is consuming its available CPU and causing sustained service CPU saturation.
- **Corroborating evidence:** High CPU usage or throttling across every `teastore-registry` pod, increased latency or errors on that service, and no single-node concentration support a service-wide CPU problem rather than an HPA, dependency, or cluster-network issue.

## Recommended remediation

- Increase `teastore-registry` CPU requests and limits using measured usage, throttling, and available node capacity as the sizing basis.
- Do not add registry replicas or an HPA. The catalog is in-memory, so extra instances split registrations instead of sharing load.
- Apply the resource change as a controlled rollout that preserves the single registry replica.
- Verify that CPU usage and throttling fall across `teastore-registry` and that latency, errors, traffic, endpoint health, and downstream request completion recover.
