# Historical Cluster Profiler Plan

## 1. Purpose

Replace transcript-style session memory with an evidence-backed historical
profile of the Kubernetes cluster. A dedicated worker will observe the cluster
continuously, build multi-granularity rollups, learn normal workload, service,
and node behaviour, and expose compact historical context to the incident
orchestrator.

The historical profiler is not a replacement for the orchestrator's mandatory
live `cluster.profile_baseline` call. The live profile establishes current
truth. Historical profiles provide comparison points, expected ranges,
recurring patterns, and prior remediation outcomes.

## 2. Goals

- Learn normal behaviour for each Deployment, pod cohort, Service, and node.
- Describe normal behaviour as a distribution and operating context, not as one
  average value.
- Preserve Kubernetes state that Prometheus alone may not retain, including pod
  placement, requests and limits, rollout identity, endpoint readiness, and HPA
  configuration.
- Produce rollups suitable for recent incident comparison and longer-term
  capacity analysis.
- Detect behavioural and configuration changes without requiring an incident
  session to occur.
- Identify recurring correlations such as one workload becoming slow whenever
  it runs on a particular node.
- Give the orchestrator bounded and relevant historical context rather than all
  previous sessions.
- Track coverage and missing signals so absent data is never interpreted as
  healthy behaviour.
- Keep collection and aggregation deterministic. Use an LLM only to render an
  optional human-readable summary from structured evidence.

## 3. Non-goals

- Replacing Prometheus as the source of full-resolution time-series metrics.
- Running a complete incident investigation every 30 seconds.
- Running expensive active network, log, or trace investigations continuously.
- Treating historically common behaviour as automatically healthy.
- Automatically changing cluster resources from profiler findings.
- Persisting unbounded raw tool output or complete agent conversations.

## 4. Key Design Principles

### 4.1 Current state remains authoritative

Every incident begins with a live baseline. Historical information may suggest
hypotheses, but current validated evidence takes precedence.

### 4.2 Usual is not the same as healthy

The profiler must maintain two independent assessments:

- **Expectedness:** whether the observation is within the historically learned
  operating range.
- **Health:** whether the observation satisfies readiness, availability,
  pressure, error, latency, and configured policy requirements.

A service that usually consumes 180% of its memory request may be historically
expected but still represent a persistent sizing risk.

### 4.3 Normal behaviour is contextual

Baselines should be conditioned where sufficient data exists by:

- resource identity and configuration generation;
- traffic or workload band;
- replica count;
- pod placement or node cohort;
- time of day and day of week;
- rollout or application version identity when available;
- HPA-active versus fixed-replica operation.

This prevents, for example, a quiet overnight period from becoming the normal
comparison for peak traffic.

### 4.4 Preserve raw evidence separately from summaries

Structured observations and rollups are the durable evidence. Narrative
summaries are derived views that can be regenerated.

### 4.5 Prefer passive collection

The 30-second loop should use passive metrics and read-only Kubernetes state.
Active network probes, broad Loki searches, and Jaeger trace analysis must run
less frequently or only in response to an anomaly.

## 5. Proposed Data Flow

```text
Prometheus + Kubernetes + passive network coverage
                         |
                         v
              Historical Profile Worker
                         |
             normalized observations (30s)
                         |
                         v
               deterministic rollups
             5m -> 30m -> 6h -> 24h -> 7d
                         |
          +--------------+----------------+
          |                               |
          v                               v
 learned normal profiles          change/pattern records
          |                               |
          +--------------+----------------+
                         v
              historical context query
                         |
                         v
 live baseline -> relevant comparison -> incident investigation
```

## 6. Collection Cadence

The worker may wake every 30 seconds, but it should not execute every collector
on every wake-up.

| Cadence | Collection | Reason |
|---|---|---|
| 30 seconds | Passive service and node metrics; lightweight readiness, replica, restart, and endpoint counters | Captures short-lived changes and aligns with common Prometheus scrape intervals |
| 2-5 minutes | Deployments, ReplicaSets, pods, Services, endpoints, HPAs, requests, limits, placement, node conditions and allocatable capacity | Kubernetes inventory changes less frequently and is more expensive than metric reads |
| 10-30 minutes | Passive probe coverage and bounded overlay/underlay latency matrix | Useful historical network comparison without continuously generating probe traffic |
| On detected change | Refresh affected resource inventory and configuration fingerprint | Records rollouts, scaling, placement, and configuration changes promptly |
| On anomaly or investigation | Bounded Loki samples, Jaeger traces, focused network path/DNS/TCP/bandwidth checks | Expensive evidence should be hypothesis-driven |

The current `cluster.profile_baseline` should be refactored so collectors can be
called independently. The historical worker must not run the current complete
profile, including its full active directed latency matrix, every 30 seconds.

## 7. Information Extracted by the Worker

### 7.1 Workload and Deployment profile

For every Deployment:

- desired, available, updated, and ready replica counts;
- availability ratio and unavailable duration;
- pod count and ready pod count;
- restart count and restart deltas;
- rollout/configuration fingerprint;
- CPU and memory requests and limits;
- HPA presence, configured targets, current replicas, and scaling boundaries;
- observed scaling events and time to stabilize;
- pod-to-node placement distribution;
- scheduling concentration and movement between nodes;
- per-pod imbalance compared with sibling pods;
- disk and network I/O;
- data coverage and missing signals.

This supports learning:

- usual replica range for a traffic band;
- normal resource consumption per replica;
- typical restart rate;
- normal placement and redistribution patterns;
- whether one pod persistently differs from its peers;
- whether resource requests and limits match sustained observed demand;
- how quickly the workload reacts to traffic and scaling changes.

### 7.2 Service behaviour profile

For every service-facing workload:

- request rate;
- p50, p95, and p99 response time where histogram data supports them;
- HTTP success, 4xx, and 5xx rates;
- request and response byte rates;
- ready and not-ready endpoint counts;
- destination and source metric scope;
- traffic distribution across pods when labels permit it;
- dependency traffic edges derived from service-mesh metrics;
- error budget or SLO status when an SLO is configured;
- missing metric or endpoint coverage.

This supports learning:

- normal latency at comparable traffic levels;
- normal error rate and whether errors occur in bursts;
- traffic seasonality and peak periods;
- dependency-specific latency or error relationships;
- expected bytes per request and unusual payload growth;
- whether a latency change is explained by load, scaling, placement, or a
  downstream dependency.

### 7.3 Resource utilization profile

For every workload:

- CPU usage in cores;
- CPU usage per ready replica;
- CPU request and limit utilization;
- CPU throttling rate, added if the source metric is available;
- memory working set;
- memory per ready replica;
- memory request and limit utilization;
- memory slope and plateau behaviour;
- OOM kill and container termination indicators, when kube-state metrics expose
  them;
- filesystem read and write throughput;
- network I/O throughput.

This supports learning:

- stable working-set memory versus progressive memory growth;
- CPU-bound versus traffic-bound behaviour;
- over-requested or under-requested resources;
- throttling that occurs below apparent node saturation;
- resource usage that scales linearly or non-linearly with traffic;
- headroom before a request, limit, or capacity boundary is reached.

### 7.4 Node profile

For every node:

- Ready and schedulable state;
- memory, disk, and PID pressure conditions;
- CPU and memory utilization;
- capacity and allocatable resources;
- requested CPU and memory as a proportion of allocatable capacity, added from
  scheduled pod requests;
- disk read/write throughput and, where available, disk latency or utilization;
- network receive/transmit throughput;
- network drops, errors, and TCP retransmits;
- number and identity of resident workloads;
- workload counts by namespace;
- pod churn and placement changes;
- passive overlay and underlay probe coverage;
- overlay/underlay RTT, jitter, loss, and peer-specific outliers at the slower
  network collection cadence.

This supports learning:

- normal utilization and headroom for each node;
- consistently hot or underused nodes;
- scheduling imbalance;
- node-specific workload degradation;
- recurring retransmit, loss, or latency patterns;
- whether overlay degradation differs from the underlay;
- whether workload impact follows a node after rescheduling.

### 7.5 Cluster-level profile

- service and node inventory counts;
- ready versus degraded resource counts;
- total requested and allocatable CPU/memory;
- aggregate capacity headroom;
- placement balance and concentration indices;
- cluster-wide traffic, error, latency, and saturation trends;
- number of active HPAs and scaling workloads;
- coverage ratio for each data source;
- correlated service/node outliers;
- common changes such as rolling updates or broad node pressure.

### 7.6 Configuration and topology history

Record changes rather than repeatedly storing full manifests:

- Deployment generation and pod-template fingerprint;
- image identifiers when available;
- resource request/limit changes;
- replica and HPA configuration changes;
- affinity, node selector, toleration, and topology-spread fingerprints;
- Service selector and port changes;
- endpoint membership changes;
- node labels relevant to scheduling;
- service dependency edge changes;
- first seen, last seen, and duration for every configuration version.

Secrets, environment variable values, and complete manifest contents must not be
stored in historical summaries.

### 7.7 Data quality profile

For every observation and rollup:

- expected sample count;
- actual sample count;
- coverage percentage;
- stale-sample count;
- source errors and timeouts;
- missing resource signals;
- collector version;
- observation time and source data time;

No baseline should be established from a window below a configured coverage
threshold.

## 8. Metric Inventory

### 8.1 Metrics already used by the existing baseline profiler

| Category | Historical signal | Current source metric |
|---|---|---|
| Traffic | requests per second | `istio_requests_total` |
| Latency | response-time percentile | `istio_request_duration_milliseconds_bucket` |
| Errors | HTTP 5xx percentage | `istio_requests_total` |
| CPU | workload CPU usage | `container_cpu_usage_seconds_total` |
| Memory | workload working set | `container_memory_working_set_bytes` |
| Requests | CPU/memory requests | `kube_pod_container_resource_requests` |
| Limits | CPU/memory limits | `kube_pod_container_resource_limits` |
| Disk | workload filesystem throughput | `container_fs_reads_bytes_total`, `container_fs_writes_bytes_total` |
| Service network | request/response byte rate | `istio_request_bytes_sum`, `istio_response_bytes_sum` |
| Node CPU | utilization | `node_cpu_seconds_total` |
| Node memory | utilization | `node_memory_MemAvailable_bytes`, `node_memory_MemTotal_bytes` |
| Node disk | read/write throughput | `node_disk_read_bytes_total`, `node_disk_written_bytes_total` |
| Node network | receive/transmit throughput | `node_network_receive_bytes_total`, `node_network_transmit_bytes_total` |
| Node network quality | drops/errors/retransmits | `node_network_receive_drop_total`, `node_network_transmit_drop_total`, `node_network_receive_errs_total`, `node_network_transmit_errs_total`, `node_netstat_Tcp_RetransSegs` |
| Ownership | pod to ReplicaSet to Deployment | `kube_pod_owner`, `kube_replicaset_owner` |
| Replicas | desired replica count | `kube_deployment_spec_replicas` |

### 8.2 Recommended additional metrics

These additions should be capability-detected. Their absence must be recorded as
missing coverage rather than causing the collection cycle to fail.

| Category | Signal | Example metric family |
|---|---|---|
| CPU | container throttling | `container_cpu_cfs_throttled_seconds_total`, `container_cpu_cfs_periods_total` |
| Memory | OOM and last termination reason | `kube_pod_container_status_last_terminated_reason`, `kube_pod_container_status_restarts_total` |
| Kubernetes | desired/available/updated/unavailable replicas | `kube_deployment_status_*` |
| Kubernetes | pod readiness and phase | `kube_pod_status_ready`, `kube_pod_status_phase` |
| HPA | current/desired replicas and target state | `kube_horizontalpodautoscaler_status_*`, `kube_horizontalpodautoscaler_spec_*` |
| Scheduling | pod requests by node | kube-state request metrics joined with pod/node ownership |
| Node | disk latency/utilization | `node_disk_io_time_seconds_total`, `node_disk_io_time_weighted_seconds_total` |
| Node | load and filesystem space | `node_load*`, `node_filesystem_avail_bytes`, `node_filesystem_size_bytes` |
| Mesh | p50 and p99 latency | existing Istio duration histogram |
| Mesh | 4xx and response-code classes | `istio_requests_total` |
| Mesh | dependency edges | source/destination workload labels on Istio request metrics |

Metric names and labels vary by cluster deployment. Each collector must validate
the available series and record the exact query and coverage status.

## 9. Historical Granularities and Retention

| Layer | Window | Suggested retention | Primary use |
|---|---:|---:|---|
| Observation | 30 seconds | 24-48 hours | Short spikes, live comparison, rollup input |
| Short rollup | 5 minutes | 7 days | Immediate incident context and brief regressions |
| Incident rollup | 30 minutes | 30-90 days | Matches the orchestrator's default investigation window |
| Operational rollup | 6 hours | 90 days | Work cycles, repeated placement and load patterns |
| Daily rollup | 24 hours | 12 months | Capacity, stability, and configuration trends |
| Weekly profile | 7 days | 12-24 months | Seasonality and long-term planning |

Prometheus remains the source for full-resolution metric history. The 30-second
database observation should therefore contain normalized features and
Kubernetes state, not a copy of every underlying time-series sample.

Each larger rollup is produced from the next-smallest retained layer. Rollup
jobs must be idempotent and use fixed UTC time buckets.

## 10. Rollup Statistics

For numeric signals, store where meaningful:

- minimum and maximum;
- mean and standard deviation;
- median;
- p50, p90, p95, and p99;
- median absolute deviation (MAD) or another robust dispersion measure;
- first and last values;
- slope and trend classification;
- count, missing count, and coverage ratio;
- duration above requests, limits, SLOs, and learned ranges;
- longest continuous breach duration;
- change count and volatility.

For categorical/state signals, store:

- time spent in each state;
- transition count;
- first and last transition time;
- dominant state;
- current state at window close;
- affected resource set.

For placement and relationships, store:

- node occupancy distribution;
- placement concentration;
- moves between nodes;
- co-location frequency;
- dependency edge presence and traffic weight;
- latency/loss by directed node pair and network plane.

## 11. Learning Normal Behaviour

### 11.1 Baseline lifecycle

Each resource/configuration profile should have one of these states:

- `collecting`: insufficient samples;
- `candidate`: sufficient samples but limited temporal coverage;
- `established`: sample count and coverage requirements satisfied;
- `stale`: resource or configuration has not been seen recently;
- `retired`: resource or configuration was removed.

The initial recommendation is at least 24 hours for a candidate baseline and 7
days for an established daily/weekly baseline. Exact thresholds must be
configurable.

### 11.2 Robust expected ranges

Use robust statistics such as quantiles and median/MAD rather than only
mean/standard deviation. Workload data is commonly skewed by traffic bursts and
scaling events.

An expected range record should contain:

- center and lower/upper bounds;
- sample count and effective time coverage;
- model context, such as traffic and replica bands;
- configuration fingerprint;
- first trained time and last updated time;
- confidence level;
- exclusions applied during learning.

### 11.3 Conditional profiles

When enough samples are present, create profiles such as:

- latency given low, medium, or high RPS;
- CPU per replica given RPS per replica;
- memory per replica for a specific configuration generation;
- scaling response when HPA is active;
- service behaviour when placed on each node;
- node behaviour for comparable resident workload levels;
- weekday/weekend and time-of-day bands.

Avoid creating a high-cardinality profile until a minimum sample count is
available. Fall back from the most specific profile to the resource-wide
profile when necessary.

### 11.4 Training exclusions and labels

Do not silently train clearly degraded periods into the healthy baseline.
Observations should be labelled as:

- healthy candidate;
- anomalous;
- degraded by Kubernetes state;
- incident-associated;
- remediation window;
- missing/low coverage;
- unknown.

Expectedness may still be learned from all sufficiently covered observations,
but the healthy-reference model should exclude degraded, incident, and
remediation windows by default.

## 12. Derived Findings and Takeaways

The historical data should enable deterministic findings before any narrative
summary is generated.

### 12.1 Normal workload conclusions

- “Frontend normally serves 280-360 RPS with three replicas during this time
  band.”
- “Cartservice memory normally plateaus between 175-190 MiB after startup.”
- “Checkoutservice CPU scales approximately linearly with RPS until 70% request
  utilization.”
- “Productcatalogservice usually scales from two to six replicas within four
  minutes of crossing its traffic threshold.”

### 12.2 Current-versus-history conclusions

- Current latency is outside the historical p99 for the same traffic and
  replica band.
- CPU is high in absolute terms but historically expected for the present RPS.
- Memory is above its request but stable and consistent with prior healthy
  windows.
- Request rate is normal, so the present latency increase is not explained by
  traffic volume.
- The current configuration is new, so older behaviour is not directly
  comparable and confidence is reduced.

### 12.3 Capacity and resource-sizing conclusions

- A workload is consistently below 20% of its CPU request and may be
  over-requested.
- A workload spends a material portion of healthy windows above its memory
  request and is under-requested.
- A workload approaches its limit during normal peak load and has insufficient
  headroom.
- Cluster allocatable headroom is adequate overall but concentrated on nodes
  that current scheduling constraints cannot use.
- HPA scaling is repeatedly late relative to traffic growth.

These are investigation or planning findings, not automatic authorization to
change requests, limits, replicas, or HPA settings.

### 12.4 Placement and node conclusions

- Latency outliers recur only when a workload has a replica on one node.
- Multiple otherwise unrelated workloads degrade when co-located on the same
  node.
- One node has persistently higher overlay RTT while its underlay remains
  comparable with peers.
- Node network retransmits rise before service latency increases.
- Scheduling is imbalanced even though all nodes are Ready.
- Workload performance follows the workload after relocation, weakening a
  node-correlation hypothesis.

### 12.5 Reliability conclusions

- A service experiences repeated brief readiness loss after every scale-up.
- Endpoint readiness lags behind pod readiness.
- Restarts are clustered around memory-limit utilization or node pressure.
- Error bursts consistently follow dependency latency increases.
- A recovered anomaly is isolated or part of a recurring pattern.

### 12.6 Data-quality conclusions

- A result is low confidence because Prometheus coverage was incomplete.
- A service lacks mesh telemetry and cannot be compared on latency or error
  rate.
- Network history is unavailable for a node because probe coverage was missing.
- The baseline is still collecting and should not yet be called normal.

## 13. Storage Model

Use PostgreSQL, which is already part of the application, for durable profiler
state. Suggested logical tables follow; exact column types and indexes should be
defined during implementation.

### `profile_observation`

- observation timestamp and fixed bucket;
- resource kind, namespace, and name;
- configuration fingerprint;
- normalized metric/state payload (`JSONB` initially);
- coverage payload;
- collector version;
- unique key on bucket, resource, and collector version for idempotency.

### `profile_rollup`

- granularity and window start/end;
- resource identity and configuration fingerprint;
- aggregate statistics;
- state durations and transitions;
- coverage and sample counts;
- unique key on granularity, window, and resource.

### `resource_configuration_history`

- resource identity;
- configuration fingerprint and safe summary;
- first seen and last seen;
- change type and previous fingerprint.

### `normal_profile`

- resource identity and signal;
- context dimensions and configuration fingerprint;
- expected range and robust statistics;
- baseline lifecycle state;
- sample count, coverage, confidence, and update time.

### `historical_finding`

- stable finding fingerprint;
- finding type and affected resources;
- first seen, last seen, occurrence count, and cumulative duration;
- supporting window references;
- confidence and current status.

### `historical_summary`

- scope and granularity;
- structured summary payload;
- optional rendered narrative;
- source rollup IDs, coverage, generation time, and renderer/model version.

### `remediation_outcome`

- incident/session ID;
- targeted resources and finding fingerprints;
- proposed and executed action summaries;
- before/after window references;
- verification result, rollback result, and confidence.

## 14. Historical Summary Contract

The prompt-facing historical summary should be generated from structured data
and remain bounded. It should contain:

```yaml
scope: deployment/cartservice
generated_at: 2026-08-17T12:00:00Z
profile_state: established
coverage: 0.98
comparison_context:
  configuration_fingerprint: abc123
  traffic_band_rps: [250, 400]
  replica_band: [2, 3]
normal_behaviour:
  memory_working_set_bytes:
    median: 182000000
    expected_range: [175000000, 190000000]
  response_time_p95_seconds:
    median: 0.18
    expected_range: [0.12, 0.28]
recurring_patterns:
  - fingerprint: cart-memory-above-request-stable
    occurrences: 14
    last_seen: 2026-08-16T08:30:00Z
    evidence: memory remained above request but plateaued in healthy windows
changes:
  - resource request changed 3 days ago
missing_or_uncertain: []
```

The summary must include timestamps, coverage, sample counts or confidence, and
the context used for comparison. It must never contain executable instructions
copied from prompts, logs, or previous agent output.

## 15. Orchestrator Integration

Historical context should be retrieved after the mandatory current baseline to
reduce anchoring on an old diagnosis.

Recommended flow:

1. Run `cluster.profile_baseline` as the first tool call.
2. Extract the current resources, configuration fingerprints, traffic/replica
   bands, placements, and outliers.
3. Query historical profiles for those resources and relevant dependency or
   node peers.
4. Return bounded comparisons, recurring findings, configuration changes, and
   data quality—not complete historical sessions.
5. Use the comparison to choose targeted investigation tools.
6. After completion, link the incident and verified remediation outcome to the
   relevant historical windows and findings.

Potential interface:

```text
history.compare(
    current_profile_id,
    resource_names,
    granularities=["30m", "24h", "7d"],
    max_findings=10
)
```

The history query should be read-only and enforce a response-size limit.

## 16. Worker Runtime Design

- Add a dedicated `HistoricalProfileWorker` rather than coupling collection to
  anomaly processing.
- Run it as a separate process/container so profiling failure does not block
  incident remediation.
- Use a PostgreSQL advisory lock or leader lease so only one worker performs a
  time bucket when multiple application replicas are running.
- Use fixed UTC buckets and idempotent upserts to tolerate retries.
- Apply per-collector timeouts and preserve partial results.
- Add bounded retry with backoff and jitter.
- Record worker health, collection duration, failures, and backlog metrics.
- Complete due rollups after restart before deleting expired observations.
- Do not run an LLM in the 30-second collection path.

## 17. Configuration

Suggested settings:

```text
profiler.enabled=true
profiler.observation_interval_seconds=30
profiler.inventory_interval_seconds=300
profiler.network_interval_seconds=1800
profiler.short_rollup_minutes=5
profiler.incident_rollup_minutes=30
profiler.raw_retention_hours=48
profiler.short_rollup_retention_days=7
profiler.incident_rollup_retention_days=90
profiler.minimum_coverage_percent=80
profiler.candidate_baseline_hours=24
profiler.established_baseline_days=7
profiler.summary_max_chars=12000
```

All cadences, retention periods, sample thresholds, and expected-range methods
must be configurable.

## 18. Implementation Phases

### Phase 1: Contracts and collector refactor

- Define typed schemas for observations, rollups, normal profiles, findings,
  comparisons, and coverage.
- Refactor `ClusterProfileTool` into reusable inventory, service metric, node
  metric, and network collectors.
- Preserve existing `cluster.profile_baseline` behaviour by composing the new
  collectors.
- Add stable resource and configuration fingerprint functions.
- Add unit tests proving equivalent current baseline output.

### Phase 2: Historical worker and persistence

- Add profiler configuration models and environment examples.
- Add PostgreSQL tables, indexes, migrations/bootstrap creation, and repository
  methods.
- Implement the 30-second scheduler with independent collector due times.
- Implement leader locking, fixed buckets, idempotent writes, partial-result
  handling, and retention cleanup.
- Add worker health instrumentation.

### Phase 3: Deterministic rollups

- Implement 5-minute and 30-minute numeric/state rollups.
- Add 6-hour, daily, and weekly rollups.
- Add coverage propagation and minimum-coverage rules.
- Add configuration and placement change detection.
- Add restart, readiness, scaling, saturation, and trend derivations.

### Phase 4: Normal-profile learning

- Implement baseline lifecycle states.
- Implement robust ranges using quantiles and median/MAD.
- Add traffic, replica, placement, configuration, and time-band contexts with
  minimum-sample fallbacks.
- Separate expectedness from health.
- Exclude degraded, incident, remediation, and low-coverage windows from the
  healthy-reference model.

### Phase 5: Findings and historical comparison

- Implement stable fingerprints for recurring findings.
- Correlate workload behaviour with traffic, replicas, dependencies, and node
  placement.
- Implement current-versus-history comparison across 30-minute, daily, and
  weekly scopes.
- Return evidence references, coverage, confidence, and uncertainty.

### Phase 6: Orchestrator memory replacement

- Add a bounded `history.compare` capability or equivalent manager-controlled
  post-baseline injection.
- Remove complete session entries from the orchestrator prompt.
- Retain incident/remediation records in structured storage.
- Optionally generate `MEMORY.md` as a human-readable report rather than using
  it as the source of truth.
- Add prompt-injection tests for stored log, incident, and summary text.

### Phase 7: Remediation outcome learning

- Capture pre-action and post-action comparison windows.
- Record execution, verification, rollback, and unresolved outcomes separately.
- Associate outcomes with recurring finding fingerprints.
- Surface prior actions as historical evidence, never as instructions to repeat
  them automatically.

## 19. Testing and Acceptance Criteria

### Collection

- One worker cycle never performs active bandwidth, path, DNS, TCP, log, or
  trace investigation unless separately triggered.
- Repeating a cycle for the same bucket does not create duplicate observations.
- A failed collector produces a partial observation with exact missing coverage.
- Multiple worker replicas do not collect the same bucket concurrently.

### Rollups

- Rollup statistics match known fixtures for numeric and state signals.
- Missing samples reduce coverage and do not become zero-valued observations.
- State durations and transitions are correct across bucket boundaries.
- Larger rollups are reproducible from smaller retained rollups.

### Normal profiles

- A baseline is not called established before sample and temporal requirements
  are satisfied.
- Traffic-conditioned comparisons do not use an unrelated load band when a
  matching band has enough samples.
- A new configuration fingerprint does not silently inherit high-confidence
  behaviour from an incompatible configuration.
- Common but unhealthy behaviour is reported as expected and unhealthy, not
  normal and healthy.
- Incident and low-coverage windows are excluded from healthy-reference
  training.

### Historical comparison

- A known outlier is identified against a matching historical cohort.
- A value within the matching historical range is not flagged only because it
  differs from the all-time average.
- Placement-correlated fixtures produce a node association with supporting and
  counterexample counts.
- Every conclusion contains time range, sample/coverage information, and source
  resource identity.

### Orchestrator safety

- The first incident tool call remains `cluster.profile_baseline`.
- Historical context is bounded and contains no complete previous prompt.
- Historical findings are explicitly data, not executable instructions.
- Current evidence overrides contradictory historical findings.

### Operational performance

- The 30-second worker completes within its interval under expected cluster
  size, or records backlog without overlapping itself.
- Database retention keeps storage within a measured bound.
- Profiler query load and active probe traffic stay below configured budgets.

## 20. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Full profiling every 30 seconds creates load | Split collectors by cadence and keep the fast path passive |
| Duplicate storage of Prometheus data | Store normalized features and Kubernetes state; query Prometheus for full-resolution history |
| Incident periods contaminate the baseline | Label and exclude degraded, incident, remediation, and low-coverage windows from healthy training |
| Chronic faults become accepted as normal | Keep expectedness and health as separate dimensions |
| New rollouts are compared with incompatible history | Partition by configuration fingerprint and lower confidence on fallback comparisons |
| High-cardinality contextual models | Require minimum samples and use hierarchical fallbacks |
| LLM summary drift | Make structured rollups authoritative and summaries reproducible derived views |
| Historical diagnosis anchors the agent | Retrieve history only after the live profile and include supporting/counter evidence |
| Missing telemetry appears healthy | Persist coverage, sample count, errors, and uncertainty with every result |
| Multiple replicas duplicate work | Use advisory locking, fixed buckets, and unique idempotency keys |
| Historical storage grows indefinitely | Apply tiered retention and compact rollups before deleting observations |

## 21. Recommended Initial Scope

The first useful version should implement:

1. A 30-second passive metric observation for existing service and node metrics.
2. A 5-minute Kubernetes inventory and configuration observation.
3. Five-minute, 30-minute, and 24-hour deterministic rollups.
4. Configuration fingerprints and placement history.
5. Candidate/established normal ranges using median, p05/p95, and MAD.
6. Comparisons conditioned by configuration, traffic band, and replica count.
7. Coverage-aware findings for latency, errors, CPU, memory, readiness, restarts,
   node saturation, and node-correlated behaviour.
8. A bounded historical comparison loaded after the live baseline.

Defer LLM-written narratives, traces, logs, active network history, advanced
seasonality, and remediation-effect learning until the deterministic foundation
is operating reliably.

## 22. Expected Result

After implementation, CloudAgent should be able to answer questions such as:

- Is the current workload unusual for this time and traffic level?
- What are the normal CPU, memory, latency, error, and replica ranges for this
  service?
- Is the service slow because load is higher, because each request is slower,
  or because scaling failed to keep up?
- Is the behaviour new since a rollout or configuration change?
- Does degradation recur on a particular node, placement, dependency, or
  network path?
- Is a resource request consistently misaligned with healthy observed demand?
- How much node and cluster headroom normally remains at peak load?
- Is this incident a one-off event or a recurrence of an established pattern?
- Did the last verified remediation change the relevant behaviour?
- Is the conclusion trustworthy given the available historical coverage?

The result is operational memory: a compact, testable representation of how the
cluster normally behaves and how the current system differs from that history.
