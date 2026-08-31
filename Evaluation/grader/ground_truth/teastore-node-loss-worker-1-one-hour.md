# teastore-node-loss-worker-1-one-hour

## RCA

- **Incident pattern:** Calls involving pods on `worker-node-1` are unreliable,
  with intermittent timeouts and errors rather than a uniform increase in
  processing time.
- **Affected scope:** Communication to and from the node is degraded, so several
  otherwise healthy services may fail whenever their request path crosses the
  affected host.
- **Root cause:** `worker-node-1` is experiencing material packet loss on its
  network path, consistent with a faulty interface, bad link, congested or
  dropping network device, or unstable upstream connectivity.
- **Corroborating evidence:** Retransmissions, failed probes or RPCs, endpoint
  errors, and a node-correlated failure pattern support packet loss rather than
  CPU saturation, normal autoscaling, or an application-only defect.

## Recommended remediation

- Cordon `worker-node-1` so new pods are not exposed to the unreliable path.
- Safely drain the node and recreate its workloads on healthy nodes while
  preserving disruption budgets and adequate service capacity.
- Keep the node unschedulable until the interface, cabling, switch, routing, or
  upstream network issue is repaired and packet delivery is stable.
- Verify recovery using packet-loss or retransmission evidence together with
  application errors, latency, traffic, traces, endpoint health, and replica
  readiness before returning the node to service.
