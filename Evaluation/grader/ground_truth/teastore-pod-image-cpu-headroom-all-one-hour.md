# teastore-pod-image-cpu-headroom-all-one-hour

## RCA

- **Incident pattern:** `teastore-image` work becomes delayed or fails during sustained demand while node CPU and unrelated TeaStore services remain healthy.
- **Affected scope:** Every `teastore-image` replica is constrained by the same CPU resource policy, so load balancing cannot select a replica with burst headroom.
- **Root cause:** `teastore-image` has an overly restrictive CPU configuration: its `300m` limit equals its `300m` request even though legitimate sustained processing demand exceeds that allocation.
- **Operational effect:** The low limit causes container CPU throttling, elevated latency, and pressure for the CPU-utilization HPA to add replicas even though the underlying problem is insufficient per-pod CPU headroom.
- **Corroborating evidence:** The live Deployment shows equal CPU request and limit, pods plateau near `300m`, throttling rises across replicas, and node CPU retains capacity.

## Recommended remediation

- Vertically right-size only `teastore-image` with `kubectl set resources deployment/teastore-image -n teastore --containers=teastore-image`, increasing both its CPU request and limit from the constrained values.
- Choose the new request from measured sustained CPU demand and the HPA's 70% utilization target; keep a higher limit for safe burst headroom. A suitable result must have `request < limit` and fit eligible-node capacity.
- Preserve memory settings and do not change unrelated Deployments whose current evidence shows no CPU impact.
- Verify the applied request and limit, schedulability, ready replicas, lower throttling, stable bounded HPA replica demand, and restored latency and errors.
