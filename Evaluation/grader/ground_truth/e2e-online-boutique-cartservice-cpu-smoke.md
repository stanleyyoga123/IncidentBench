# e2e-online-boutique-cartservice-cpu-smoke

## RCA

All running `cartservice` replicas in `online-boutique` are subject to recurring
CPU stress. Correct diagnosis must localize sustained CPU saturation or
throttling to that Deployment and distinguish it from node, memory, dependency,
and network faults using current evidence.

## Recommended remediation

After validating current requests, limits, throttling, demand, and node
headroom, increase only `cartservice` CPU capacity through measured vertical
right-sizing or bounded horizontal scaling. Preserve availability and verify
cart latency, errors, traffic, endpoints, replica readiness, and CPU recovery.
