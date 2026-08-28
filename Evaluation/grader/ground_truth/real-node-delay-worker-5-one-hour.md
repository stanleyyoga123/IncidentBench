# real-node-delay-worker-5-one-hour

## RCA

- **Incident pattern:** Requests that cross `worker-node-5` show persistently
  high latency and timeouts, while equivalent paths between healthy nodes
  perform normally.
- **Affected scope:** Pods on the node and services that call them are affected;
  the resulting slowdown can propagate through several downstream request
  paths even when pods remain `Running` and `Ready`.
- **Root cause:** The bidirectional network path to `worker-node-5` has severe
  latency and jitter, consistent with a degraded interface, congested link,
  faulty routing path, or remote-location connectivity problem.
- **Corroborating evidence:** Elevated inter-node RTT involving this node,
  increased service duration or timeouts, and healthy CPU, replica, and HPA
  behavior elsewhere distinguish the network path from a capacity problem.

## Recommended remediation

- Cordon `worker-node-5` to stop placing new workloads behind the degraded
  network path.
- Safely drain the node so affected pods move to nodes with healthy
  connectivity, while respecting disruption budgets and service capacity.
- Keep the node unschedulable until its interface, routing, link, or upstream
  network problem is corrected and bidirectional latency is stable.
- Verify recovery with inter-node RTT plus application latency, error, traffic,
  trace, endpoint-health, and replica evidence before returning the node to
  service.
