# e2e-node-cpu-worker-1-twenty-minutes

## RCA

- **Incident pattern:** Services with pods scheduled on `worker-node-1` become
  slow or intermittently unavailable while workloads on other nodes remain
  comparatively healthy.
- **Affected scope:** The problem is node-wide rather than isolated to one
  application, container, or request path.
- **Root cause:** `worker-node-1` is experiencing sustained host CPU
  saturation, consistent with a runaway compute-intensive process or workload
  consuming most of the node's available CPU.
- **Corroborating evidence:** High node CPU utilization, CPU throttling or
  scheduling delay across multiple colocated pods, elevated application
  latency, and recovery when workloads leave the node support this conclusion.

## Recommended remediation

- Cordon `worker-node-1` to prevent new workloads from being placed on the
  saturated host.
- Safely drain the node so affected workloads are recreated on healthy capacity
  while respecting disruption budgets and workload availability.
- Keep the node unschedulable while the CPU-consuming process or underlying
  host problem remains; do not return it to service merely because it reports
  `Ready`.
- Verify recovery through node CPU, pod throttling, application latency, error
  rate, traffic, replica health, and successful rescheduling.
