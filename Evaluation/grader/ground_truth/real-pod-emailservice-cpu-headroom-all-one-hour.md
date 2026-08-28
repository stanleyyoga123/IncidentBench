# real-pod-emailservice-cpu-headroom-all-one-hour

## RCA

- **Incident pattern:** Order-confirmation emails become delayed or fail during
  sustained demand while checkout, payment, node CPU, and memory remain healthy.
- **Affected scope:** Every `emailservice` replica is constrained by the same CPU
  resource policy, so load balancing cannot select a replica with burst
  headroom.
- **Root cause:** `emailservice` has an overly restrictive CPU configuration:
  its `250m` limit equals its `250m` request even though legitimate sustained
  processing demand exceeds that allocation.
- **Operational effect:** The low limit causes container CPU throttling, email
  queue growth, elevated RPC duration, and pressure for the CPU-utilization HPA
  to add replicas even though the underlying problem is insufficient per-pod
  CPU headroom.
- **Corroborating evidence:** The live Deployment shows equal CPU request and
  limit, all email pods plateau near `250m`, throttling rises across replicas,
  node CPU retains capacity, and email-specific latency follows the throttling.

## Recommended remediation

- Vertically right-size only `emailservice` with `kubectl set resources
  deployment/emailservice -n online-boutique --containers=server`, increasing
  both its CPU request and limit from the constrained values.
- Choose the new request from measured sustained CPU demand and the HPA's 70%
  utilization target; keep a higher limit for safe burst headroom. A suitable
  result must have `request < limit` and fit eligible-node capacity.
- Preserve memory settings and do not change unrelated Deployments whose current
  evidence shows no CPU impact.
- Verify the applied request and limit, schedulability, ready replicas, lower
  throttling, stable bounded HPA replica demand, drained email work, restored
  email latency and errors, and successful order confirmations.
