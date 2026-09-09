# long-multi-fault-one-day

This scenario contains four sequential active fault phases separated by idle recovery periods. Faults are not simultaneous. Grade each RCA and remediation against the phase identified by its current evidence; a result does not need to diagnose future phases.

## RCA

### Authoritative phases

1. **Worker-node-3 bidirectional delay:** two recurring PhysicalMachineChaos schedules impose 250 ms latency, 50 ms jitter, and 25% correlation on `worker-node-3` and every peer path to it for 25 seconds of each 30-second cycle.
2. **Worker-node-3 packet loss:** recurring PhysicalMachineChaos injects 20% loss with 25% correlation on `worker-node-3` `eth0` for 25 seconds of each 30-second cycle.
3. **Product catalog CPU:** recurring StressChaos adds one 45% CPU worker to every Running `productcatalogservice` replica for 25 seconds of each 30-second cycle.
4. **Worker-node-5 bidirectional delay:** the same two-sided 250 ms/50 ms-jitter delay pattern targets `worker-node-5`.

### Expected diagnosis and evidence

- A full RCA identifies the currently active phase, exact node or workload, fault dimension, selector scope, and correlated impact. Node-network phases affect multiple services by placement; the product-catalog phase follows one Deployment across nodes.
- Node delay requires RTT/trace latency correlated with the named node; packet loss requires failed probes, retransmission-like behavior, or errors correlated with `worker-node-3`; catalog CPU requires CPU/throttling across all catalog replicas without a single-node concentration.
- During an idle phase, the expected conclusion is that no scenario fault is active unless current evidence proves a persistent effect. A stale earlier anomaly is not evidence of a current fault.

## Recommended remediation

### Fully correct

- For an active node-network phase, validate capacity and disruption risk, cordon and safely drain only the currently affected node, and leave it unschedulable until the fault ends and current recovery evidence supports uncordon.
- For the catalog CPU phase, increase only `productcatalogservice` CPU capacity through measured vertical sizing or bounded horizontal scaling with an explicit capacity-tested maximum.
- During idle recovery, avoid a new disruptive mutation. Validate any isolated node before restoring it and preserve safe state when recovery is ambiguous.

### Helpful but incomplete

- Cordon-only or relocating one affected workload can partially mitigate a node phase. A conservative one-dimensional catalog CPU change or bounded temporary scale-out can partially mitigate the service phase.

### Rejected approaches

- Acting on the wrong phase, node, or service; uncordoning an actively impaired node; combining aggressive catalog scale-out with oversized requests; or repeatedly restarting workloads is unsafe or counterproductive.
- Version rollback, disabling outbound or dependency calls, bypassing the tested function, scaling the workload to zero, or deleting or modifying the Chaos Mesh Schedule/injected host state are not accepted simulation remediations.

### Verification

- Verify phase-specific node RTT/loss or catalog CPU evidence, schedulability and Ready replicas, and response-time P95 plus HTTP 5xx recovery before declaring success.
