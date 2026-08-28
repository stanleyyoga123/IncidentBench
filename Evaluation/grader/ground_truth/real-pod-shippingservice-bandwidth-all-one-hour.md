# real-pod-shippingservice-bandwidth-all-one-hour

## RCA

- **Incident pattern:** Shipping quote and order-shipment calls slow as traffic
  grows, delaying checkout even though CPU, memory, readiness, and dependencies
  remain healthy.
- **Affected scope:** Every `shippingservice` replica reaches an independent
  per-pod network throughput ceiling, constraining aggregate service throughput.
- **Root cause:** `shippingservice` has insufficient horizontal capacity for its
  per-instance bandwidth limit, consistent with a CNI, sidecar, interface, or
  platform rate ceiling applied to each pod.
- **Corroborating evidence:** Per-pod network throughput plateaus, queues and RPC
  duration grow with load, CPU remains below saturation, and traffic is balanced
  across otherwise healthy shipping endpoints.

## Recommended remediation

- Use `kubectl patch hpa shippingservice-hpa -n online-boutique` to raise
  `minReplicas`, distributing traffic across more independently limited pods.
- Set an explicit, capacity-tested `maxReplicas` in the same patch so scale-out
  cannot create excessive instances or exhaust cluster resources.
- Do not increase CPU or memory when the observed constraint is network
  throughput; keep the remediation scoped to bounded aggregate capacity.
- Verify HPA bounds, desired and ready replicas, reduced traffic per pod,
  improved aggregate throughput, shipping latency and errors, endpoint health,
  and completed checkout shipping calls.
