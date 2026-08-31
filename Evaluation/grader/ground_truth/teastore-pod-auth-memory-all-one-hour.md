# teastore-pod-auth-memory-all-one-hour

## RCA

- **Incident pattern:** Authentication and session operations slow, fail, or disappear while other TeaStore functions may remain available.
- **Affected scope:** All running `teastore-auth` replicas exhibit elevated memory use, so traffic cannot be routed to an unaffected instance.
- **Root cause:** `teastore-auth` is vertically under-sized for a sustained increase in its normal working set, causing every replica to approach its container memory limit.
- **Corroborating evidence:** High working-set and memory-limit utilization across every `teastore-auth` pod, OOM termination evidence, and service-specific latency or errors distinguish the issue from node-wide pressure or a WebUI defect.

## Recommended remediation

- Vertically right-size the workload with `kubectl set resources deployment/teastore-auth -n teastore`, increasing memory requests and limits using observed working-set growth and available node capacity as the sizing basis.
- Preserve the existing CPU settings unless current evidence also justifies a CPU change.
- Confirm the increased memory request fits eligible-node capacity and does not make required replicas unschedulable.
- Verify stable memory headroom without new OOM kills, healthy replicas, restored latency and errors, and normal storefront traffic.
