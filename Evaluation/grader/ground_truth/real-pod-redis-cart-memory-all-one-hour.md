# real-pod-redis-cart-memory-all-one-hour

## RCA

- **Incident pattern:** Cart reads and updates slow or fail as Redis approaches
  its container memory limit, while Redis remains network-reachable and node
  memory remains healthy.
- **Affected scope:** All `redis-cart` replicas have inadequate memory headroom
  for their working set and a fixed additional allocation.
- **Root cause:** `redis-cart` is vertically under-sized, causing sustained memory
  pressure and risk of OOM termination as the in-memory dataset or cache grows.
- **Corroborating evidence:** High Redis working-set and limit utilization,
  memory-allocation or OOM evidence, healthy node memory, and cart-specific
  degradation distinguish the problem from a node or network incident.

## Recommended remediation

- Vertically right-size Redis with `kubectl set resources deployment/redis-cart
  -n online-boutique --containers=redis`, increasing memory requests and limits
  enough for the measured working set plus safe headroom.
- Confirm that the requested memory fits available node capacity and preserve the
  existing CPU settings unless evidence justifies changing them.
- Do not use horizontal scaling as a substitute for memory headroom because the
  current Redis Deployment is not configured as a sharded data tier.
- Verify the applied requests and limits, stable memory utilization below the new
  limit, absence of OOM events, ready Redis endpoints, cart latency and errors,
  and successful cart operations.
