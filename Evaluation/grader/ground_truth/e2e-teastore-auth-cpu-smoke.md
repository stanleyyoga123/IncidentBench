# e2e-teastore-auth-cpu-smoke

## RCA

All running `teastore-auth` replicas in `teastore` are subject to recurring CPU stress. Correct diagnosis must localize sustained CPU saturation or throttling to that Deployment and distinguish it from node, memory, dependency, and network faults using current evidence.

## Recommended remediation

After validating current requests, limits, throttling, demand, and node headroom, increase only `teastore-auth` CPU capacity through measured vertical right-sizing or bounded horizontal scaling. Preserve availability and verify login latency, errors, traffic, endpoints, replica readiness, and CPU recovery.
