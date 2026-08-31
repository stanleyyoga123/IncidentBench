# teastore-pod-image-bandwidth-all-one-hour

## RCA

- **Incident pattern:** `teastore-image` responses become slow while CPU and memory on the same pods remain comparatively healthy.
- **Affected scope:** Every running `teastore-image` replica is bandwidth-capped, so adding traffic without more replicas cannot restore throughput.
- **Root cause:** A per-pod network bandwidth ceiling limits `teastore-image` rather than compute saturation or a node-wide network fault.
- **Corroborating evidence:** Low per-pod throughput with unused CPU, healthy node links, and service-specific latency support a bandwidth bottleneck that horizontal scaling can absorb.

## Recommended remediation

- Increase aggregate `teastore-image` throughput with `kubectl patch hpa teastore-image-hpa -n teastore`, raising replica bounds so more pods share the per-pod bandwidth cap.
- Set an explicit, capacity-tested `maxReplicas` and do not treat CPU or memory as the primary fix.
- Verify HPA bounds, ready replicas, restored latency and errors, and improved service throughput.
