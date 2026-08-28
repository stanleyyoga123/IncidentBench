# real-pod-checkoutservice-cpu-headroom-all-one-hour

## RCA

- **Incident pattern:** Checkout latency and errors increase during sustained
  transaction demand while browsing, node CPU, and memory remain healthy.
- **Affected scope:** Every `checkoutservice` replica is constrained by the same
  CPU resource policy, leaving no pod with burst headroom for orchestration work.
- **Root cause:** `checkoutservice` has an overly restrictive CPU configuration:
  its `250m` limit equals its `250m` request even though legitimate checkout
  processing demand exceeds that allocation.
- **Operational effect:** CPU throttling delays the checkout orchestration path
  and increases CPU-utilization HPA demand; adding identically constrained pods
  does not correct the insufficient per-pod allocation.
- **Corroborating evidence:** The Deployment shows equal request and limit, all
  checkout pods plateau near `250m`, throttling rises across replicas, nodes
  retain CPU capacity, and downstream calls wait behind checkout processing.

## Recommended remediation

- Vertically right-size only `checkoutservice` with `kubectl set resources
  deployment/checkoutservice -n online-boutique --containers=server`, increasing
  both its CPU request and limit from the constrained values.
- Derive the request from measured sustained CPU demand and the HPA's 70%
  utilization target, then set a higher limit for safe bursts. The resulting
  configuration must have `request < limit` and fit eligible-node capacity.
- Preserve memory and transaction settings, and do not change downstream
  services whose current evidence is healthy.
- Verify the applied resources, schedulability, ready replicas, lower throttling,
  stable bounded HPA demand, checkout latency and errors, successful downstream
  calls, and completed transactions.
