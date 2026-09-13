# Evaluation scenarios

This document summarizes the 47 currently planned scenarios in
`Evaluation/collections`: 23 Online Boutique scenarios, 23 TeaStore scenarios,
and one Sock Shop scenario. The collection JSON and referenced Chaos Mesh manifests remain
evaluator-only inputs for exact execution timing and reproducibility; the
catalogue below describes only the production-observable incident condition.
The remediation descriptions match the grader ground-truth policy in
[`grader/scenario-policy.md`](../grader/scenario-policy.md).
The paper-level aggregation and reporting method is defined in
[`evaluation_plan.md`](evaluation_plan.md).

## Remediation types

| Remediation type | Fault type | Expected approach |
| --- | --- | --- |
| Node isolation and evacuation | Node network delay, packet loss, CPU pressure, or memory pressure | Confirm the affected node and available capacity, cordon it, safely drain movable workloads while respecting disruption and storage constraints, and keep it isolated until host recovery is demonstrated. Cordon-only or bounded relocation is helpful but incomplete. |
| Service CPU capacity | CPU pressure across all target pods | Use observed demand to vertically right-size CPU or apply bounded horizontal scaling when the service is safe to replicate. Verify rollout, scheduling, saturation, latency, errors, and the dependent path. |
| Service memory capacity | Memory pressure across all target pods | Vertically right-size memory requests and limits from measured working-set and OOM evidence. Horizontal scaling is not a substitute for per-pod memory pressure and is unsafe for the current Redis and database state models. |
| Bandwidth scale-out | Per-pod bandwidth throttling across all target pods | Increase aggregate throughput with a bounded, capacity-tested HPA minimum and maximum. A safe direct replica increase is helpful but incomplete. |
| N+1 capacity | Recurring loss of one target pod | Add durable, bounded N+1 capacity through HPA settings so one lost pod does not remove required service capacity. A safe direct replica increase is partial credit. |
| CPU headroom | CPU demand reaches an equal request/limit configuration with insufficient burst headroom | Raise both CPU request and limit using measured demand, keep `request < limit`, and ensure the pod remains schedulable. A safe limit-only increase is helpful but incomplete. |

All remediation types reject actions that do not address the observed
condition or create disproportionate risk, including version rollback without
version evidence, disabling dependency traffic, bypassing the tested function,
scaling a workload to zero, or deleting nodes, namespaces, workloads, or data
as the incident fix. Evaluator anti-tampering rules remain separate penalty
criteria and are not semantic ground truth.

## Online Boutique scenarios

| # | Scenario | Fault type | Target | Remediation type |
| ---: | --- | --- | --- | --- |
| 1 | `real-node-delay-worker-3-one-hour` | Bidirectional node network delay | `worker-node-3` and traffic between it and peer nodes | Node isolation and evacuation |
| 2 | `real-node-delay-worker-2-one-hour` | Bidirectional node network delay | `worker-node-2` and traffic between it and peer nodes | Node isolation and evacuation |
| 3 | `real-node-delay-worker-5-one-hour` | Bidirectional node network delay | `worker-node-5` and traffic between it and peer nodes | Node isolation and evacuation |
| 4 | `real-node-loss-worker-1-one-hour` | Node packet loss | `worker-node-1` | Node isolation and evacuation |
| 5 | `real-node-loss-worker-2-one-hour` | Node packet loss | `worker-node-2` | Node isolation and evacuation |
| 6 | `real-node-loss-worker-3-one-hour` | Node packet loss | `worker-node-3` | Node isolation and evacuation |
| 7 | `real-pod-cartservice-cpu-all-one-hour` | Service-wide pod CPU pressure | `cartservice` | Service CPU capacity |
| 8 | `real-pod-checkoutservice-cpu-all-one-hour` | Service-wide pod CPU pressure | `checkoutservice` | Service CPU capacity |
| 9 | `real-pod-recommendationservice-cpu-all-one-hour` | Service-wide pod CPU pressure | `recommendationservice` | Service CPU capacity |
| 10 | `real-pod-productcatalogservice-cpu-all-one-hour` | Service-wide pod CPU pressure | `productcatalogservice` | Service CPU capacity |
| 11 | `real-pod-paymentservice-cpu-all-one-hour` | Service-wide pod CPU pressure | `paymentservice` | Service CPU capacity |
| 12 | `real-node-cpu-worker-2-one-hour` | Node CPU pressure | `worker-node-2` | Node isolation and evacuation |
| 13 | `real-node-memory-worker-3-one-hour` | Node memory pressure | `worker-node-3` | Node isolation and evacuation |
| 14 | `real-pod-adservice-memory-all-one-hour` | Service-wide pod memory pressure | `adservice` | Service memory capacity |
| 15 | `real-pod-checkoutservice-capacity-loss-one-hour` | Recurring single-pod capacity loss | `checkoutservice` | N+1 capacity |
| 16 | `real-pod-productcatalogservice-bandwidth-all-one-hour` | Per-pod bandwidth throttling | `productcatalogservice` | Bandwidth scale-out |
| 17 | `real-pod-redis-cart-memory-all-one-hour` | Service-wide pod memory pressure | `redis-cart` | Service memory capacity; vertical-only for state safety |
| 18 | `real-pod-currencyservice-memory-all-one-hour` | Service-wide pod memory pressure | `currencyservice` | Service memory capacity |
| 19 | `real-pod-shippingservice-bandwidth-all-one-hour` | Per-pod bandwidth throttling | `shippingservice` | Bandwidth scale-out |
| 20 | `real-pod-paymentservice-capacity-loss-one-hour` | Recurring single-pod capacity loss | `paymentservice` | N+1 capacity |
| 21 | `real-pod-emailservice-cpu-headroom-all-one-hour` | CPU headroom pressure | `emailservice` | CPU headroom |
| 22 | `real-pod-checkoutservice-cpu-headroom-all-one-hour` | CPU headroom pressure | `checkoutservice` | CPU headroom |
| 23 | `real-pod-productcatalogservice-cpu-headroom-all-one-hour` | CPU headroom pressure | `productcatalogservice` | CPU headroom |

Online Boutique checkout and payment targets sit on transactional paths, so
recovery verification must include the affected checkout/payment workflow and
not only pod health. `redis-cart` remediation must preserve cart state.

## TeaStore scenarios

| # | Scenario | Fault type | Target | Remediation type |
| ---: | --- | --- | --- | --- |
| 1 | `teastore-node-delay-worker-3-one-hour` | Bidirectional node network delay | `worker-node-3` and traffic between it and peer nodes | Node isolation and evacuation |
| 2 | `teastore-node-delay-worker-2-one-hour` | Bidirectional node network delay | `worker-node-2` and traffic between it and peer nodes | Node isolation and evacuation |
| 3 | `teastore-node-delay-worker-5-one-hour` | Bidirectional node network delay | `worker-node-5` and traffic between it and peer nodes | Node isolation and evacuation |
| 4 | `teastore-node-loss-worker-1-one-hour` | Node packet loss | `worker-node-1` | Node isolation and evacuation |
| 5 | `teastore-node-loss-worker-2-one-hour` | Node packet loss | `worker-node-2` | Node isolation and evacuation |
| 6 | `teastore-node-loss-worker-3-one-hour` | Node packet loss | `worker-node-3` | Node isolation and evacuation |
| 7 | `teastore-pod-auth-cpu-all-one-hour` | Service-wide pod CPU pressure | `teastore-auth` | Service CPU capacity |
| 8 | `teastore-pod-persistence-cpu-all-one-hour` | Service-wide pod CPU pressure | `teastore-persistence` | Service CPU capacity |
| 9 | `teastore-pod-recommender-cpu-all-one-hour` | Service-wide pod CPU pressure | `teastore-recommender` | Service CPU capacity |
| 10 | `teastore-pod-image-cpu-all-one-hour` | Service-wide pod CPU pressure | `teastore-image` | Service CPU capacity |
| 11 | `teastore-pod-registry-cpu-all-one-hour` | Service-wide pod CPU pressure | `teastore-registry` | Registry vertical CPU |
| 12 | `teastore-node-cpu-worker-2-one-hour` | Node CPU pressure | `worker-node-2` | Node isolation and evacuation |
| 13 | `teastore-node-memory-worker-3-one-hour` | Node memory pressure | `worker-node-3` | Node isolation and evacuation |
| 14 | `teastore-pod-image-memory-all-one-hour` | Service-wide pod memory pressure | `teastore-image` | Service memory capacity |
| 15 | `teastore-pod-persistence-capacity-loss-one-hour` | Recurring single-pod capacity loss | `teastore-persistence` | N+1 capacity |
| 16 | `teastore-pod-image-bandwidth-all-one-hour` | Per-pod bandwidth throttling | `teastore-image` | Bandwidth scale-out |
| 17 | `teastore-pod-db-memory-all-one-hour` | Service-wide pod memory pressure | `teastore-db` | Service memory capacity; vertical-only for database state safety |
| 18 | `teastore-pod-auth-memory-all-one-hour` | Service-wide pod memory pressure | `teastore-auth` | Service memory capacity |
| 19 | `teastore-pod-recommender-bandwidth-all-one-hour` | Per-pod bandwidth throttling | `teastore-recommender` | Bandwidth scale-out |
| 20 | `teastore-pod-registry-capacity-loss-one-hour` | Recurring single-pod capacity loss | `teastore-registry` | Registry single-replica recovery |
| 21 | `teastore-pod-webui-cpu-headroom-all-one-hour` | CPU headroom pressure | `teastore-webui` | CPU headroom |
| 22 | `teastore-pod-persistence-cpu-headroom-all-one-hour` | CPU headroom pressure | `teastore-persistence` | CPU headroom |
| 23 | `teastore-pod-image-cpu-headroom-all-one-hour` | CPU headroom pressure | `teastore-image` | CPU headroom |

TeaStore registry scenarios must preserve its single non-shared in-memory
registry. Horizontal registry scaling can split service-discovery state.
Database remediation must preserve database state and remain vertical-only.

## Sock Shop scenario

| # | Scenario | Fault type | Target | Remediation type |
| ---: | --- | --- | --- | --- |
| 1 | `sock-shop-pod-catalogue-cpu-all-ten-minutes` | Service-wide pod CPU pressure | `catalogue` | Service CPU capacity |

The Sock Shop scenario window is exactly 600 seconds: 300 seconds of recurring
CPU pressure followed by 300 seconds of recovery. Setup, the 60-second
application warm-up, and baseline collection happen before this window.

## Recovery checks

For every scenario, verify the applied workload or node state, rollout and
schedulability, desired versus Ready replicas, condition-specific evidence, and
the affected user/dependency path. The grader's five-minute metric comparison
uses only `response_time_p95_seconds` and `http_5xx_rate`; other captured
metrics may support diagnosis but do not affect the metric grade.
