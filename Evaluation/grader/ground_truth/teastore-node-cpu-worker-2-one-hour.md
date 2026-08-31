# teastore-node-cpu-worker-2-one-hour

## RCA

- **Incident pattern:** Multiple unrelated services become slow when their pods
  run on `worker-node-2`, while replicas on other nodes remain comparatively
  healthy.
- **Affected scope:** The degradation is node-wide and crosses application
  boundaries rather than following one Deployment or request path.
- **Root cause:** `worker-node-2` has sustained host CPU saturation, consistent
  with a runaway process, misconfigured system workload, or noisy-neighbour
  workload consuming most available compute time.
- **Corroborating evidence:** High node CPU utilization, throttling or scheduling
  delay across colocated pods, degraded application latency, and improvement
  after workloads leave the node distinguish this from service-only demand.

## Recommended remediation

- Cordon `worker-node-2` so no new workloads are scheduled onto the saturated
  host.
- Safely drain evictable workloads to healthy nodes while respecting disruption
  budgets, local-data constraints, and replacement capacity.
- Keep the node unschedulable until the CPU-consuming process or host problem is
  identified and stopped; a Kubernetes `Ready` condition alone is insufficient.
- Verify lower node CPU, healthy replacement pods, completed rollouts, restored
  latency and traffic, and stable error rates before returning the node to
  service.
