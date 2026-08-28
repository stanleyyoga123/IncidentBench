# long-multi-fault-one-day

This scenario contains four sequential fault phases separated by idle recovery
periods. The faults are not injected simultaneously. An individual RCA or
remediation result should be evaluated against the active phase it identifies;
it does not need to diagnose or remediate all four phases at once. During an
idle period, the expected conclusion is that no scenario fault is currently
active, unless current evidence supports a persistent effect from an earlier
phase.

## RCA

### Phase 1: worker-node-3 bidirectional network delay

- **Incident pattern:** Requests crossing `worker-node-3` exhibit sustained
  latency, jitter, and possible timeouts, while paths that avoid the node are
  comparatively healthy. Pods may remain `Running` and `Ready` despite the
  degraded request path.
- **Affected scope:** Pods placed on `worker-node-3`, their callers, and
  downstream request paths that cross the node.
- **Root cause:** Severe bidirectional network delay involving
  `worker-node-3`. The archived schedules inject approximately 250 ms latency,
  50 ms jitter, and 25% correlation on the node and on peer traffic destined
  for it.
- **Corroborating evidence:** Elevated inter-node RTT involving
  `worker-node-3`, service or trace latency correlated with workloads on that
  node, and comparatively normal CPU, replica, and healthy-node behavior.

### Phase 2: worker-node-3 packet loss

- **Incident pattern:** Calls involving pods on `worker-node-3` fail
  intermittently or time out rather than showing only a uniform processing
  delay.
- **Affected scope:** Communication from the affected node is unreliable, so
  multiple services can fail when a request path reaches a pod placed there.
- **Root cause:** Material network packet loss on `worker-node-3`. The archived
  schedule injects 20% loss with 25% correlation on `eth0`.
- **Corroborating evidence:** Failed probes or RPCs, retransmission-like
  behavior, elevated errors, and a node-correlated failure pattern distinguish
  packet loss from CPU saturation or an application-only defect.

### Phase 3: productcatalogservice CPU saturation

- **Incident pattern:** Product listing, search, and product-detail requests
  slow down or fail, with secondary effects on callers that require catalog
  data.
- **Affected scope:** Every running `productcatalogservice` replica is subject
  to the injected CPU stress, so load balancing cannot select an unaffected
  catalog instance.
- **Root cause:** Service-wide CPU pressure in `productcatalogservice`. The
  archived schedule runs one CPU stress worker at 45% load in all running
  `productcatalogservice` pods.
- **Corroborating evidence:** Elevated CPU usage or throttling across the
  catalog replicas, catalog-specific latency or errors, and no consistent
  single-node concentration distinguish this phase from either node-network
  phase.

### Phase 4: worker-node-5 bidirectional network delay

- **Incident pattern:** Requests crossing `worker-node-5` exhibit sustained
  latency, jitter, and possible timeouts, while equivalent paths between other
  nodes are comparatively healthy.
- **Affected scope:** Pods placed on `worker-node-5`, their callers, and
  downstream paths that cross the node.
- **Root cause:** Severe bidirectional network delay involving
  `worker-node-5`. The archived schedules inject approximately 250 ms latency,
  50 ms jitter, and 25% correlation on the node and on peer traffic destined
  for it.
- **Corroborating evidence:** Elevated inter-node RTT involving
  `worker-node-5`, latency correlated with workloads on that node, and healthy
  CPU, replica, and network behavior elsewhere.

## Recommended remediation

### For either node-delay phase

- Cordon the currently affected node—`worker-node-3` in Phase 1 or
  `worker-node-5` in Phase 4—to stop placing new workloads behind the degraded
  path.
- Safely drain that node so affected pods are recreated on nodes with healthy
  connectivity, while respecting disruption budgets and available capacity.
- Keep the node unschedulable while the delay remains. After the fault has
  ended or the underlying interface, link, routing, or upstream problem has
  been corrected, require stable bidirectional RTT and application-health
  evidence before uncordoning it.
- Verify inter-node RTT together with application latency, errors, traffic,
  traces, endpoint health, replica readiness, and successful rescheduling.

### For the worker-node-3 packet-loss phase

- Cordon `worker-node-3` and safely drain its workloads to healthy nodes while
  preserving disruption budgets and service capacity.
- Keep `worker-node-3` unschedulable while packet loss persists. Return it to
  service only after the injection has ended or the interface, cabling,
  switch, routing, or upstream problem is repaired and packet delivery is
  stable.
- Verify packet loss, failed probes or retransmissions together with
  application error rate, latency, traffic, traces, endpoint health, and
  replica readiness.

### For the productcatalogservice CPU phase

- Prefer measured vertical scaling when the existing replicas can safely
  carry the workload: increase `productcatalogservice` CPU requests and limits
  using observed usage, throttling, and available node capacity as the sizing
  basis.
- Alternatively, use horizontal scaling with an explicit, capacity-tested HPA
  maximum so `productcatalogservice` gains sufficient replicas without
  excessive growth or cluster exhaustion.
- Apply the selected change as a controlled rollout and do not combine an
  aggressive replica target with oversized per-pod CPU requests.
- Verify reduced catalog CPU pressure or throttling and recovery of catalog
  latency, errors, traffic, endpoint health, search, product retrieval, and
  dependent frontend or recommendation calls.

### For idle recovery periods

- Do not perform a new disruptive remediation solely because a previous fault
  appears in the scenario definition. Confirm whether any injected condition
  is currently active and whether symptoms persist.
- If a previously isolated node has recovered, validate its network and
  application behavior before restoring schedulability. Preserve any current
  safe state when evidence is ambiguous rather than acting on a stale phase.
