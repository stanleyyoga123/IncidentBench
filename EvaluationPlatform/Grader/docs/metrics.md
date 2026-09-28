# Metric reference

Default methodology: `archive-recovery-v3`. Original Runner archives are sufficient. See [methodology](methodology.md) for eligibility, incident boundaries, uncertainty and interpretation; see [portable evidence](evidence-contract.md) for field contracts.

## Which metrics appear where?

The CLI currently writes five CSV files under `<output>/csvs/`, plus per-run
`grade.json`, `report.md`, `judge-cache.json`, and `<output>/logs/grader.log`.

| Output | Unit of reporting | Contents |
| --- | --- | --- |
| `scenario_table.csv` | One archived run | 14 columns: scenario, score maxima/means, session counts, trimmed-baseline and paired best P95/5xx, UTC window location, imputation counts |
| `window_comparison.csv` | Run × metric × workload × best selection | Full-baseline client mean estimate or service P95/5xx, independently selected windows, changes, coverage and imputation counts |
| `rca_rubric_score.csv` | One RCA job | Status, `is_failed`, alignment, five criterion classes/scores and weighted total |
| `remediation_rubric_score.csv` | One remediation job | Status, `is_failed`, alignment, five criterion classes/scores, rubric total, penalties and final total |
| `summary.csv` | One exported job | Identity, methodology/policy, status, semantic score/alignment and compatibility fields |
| `runs/<run>/grade.json` | One archived run | Job grading plus `window_comparison`, `paired_window`, and `research` evidence and outcomes |

A run with no exported jobs has no rows in the job CSVs; it still
has a scenario-table row and per-run JSON. Use those run-level outputs for run
counts. The scenario CSV contains the scenario name but no unique run column;
repeated scenario names must be distinguished using per-run JSON/directories.

### Three different baseline definitions

| Measurement | Baseline used | Chaos/incident selection |
| --- | --- | --- |
| Independent `window_comparison` | Full recorded baseline | Lowest covered value independently for each metric and workload |
| Paired `scenario_table` / `paired_window` | Recorded baseline excluding first 5 minutes by default | Lowest P95 with 5xx ≤0.5 requests/s; paired P95/5xx values share one window |
| `research.operational` recovery proxy | Last 5 minutes of baseline by default, from evaluation policy | Sustained qualifying 30-second bins after observed degradation; separate from descriptive window selection |

`--baseline-ignore-minutes` affects only the paired table. It does not change
independent comparisons or recovery policy. `--comparison-window-minutes`
(default 5) affects both descriptive comparisons, not the recovery bin size.

## Collected telemetry: 13 existing families plus an offline-derived error ratio

Resource entries below are diagnostic. Service latency and traffic additionally support the explicitly labelled archive recovery proxy. Read `metrics/<name>.json` → `data.result[]` → `metric` and `values`. Preserve each label set. Counter rates use the archived query window (default 1 minute); gauges are point samples. Raw telemetry and recovery calculations do not fill missing, NaN, infinite or unmatched series with zero. Descriptive window comparisons have the explicit HTTP 5xx exception documented below. Historical availability depends on the archived metric file, not on whether the name exists in code. The Runner collector is unchanged. The Grader derives `derived_http_5xx_ratio` offline from matching `http_5xx_rate` and `traffic_rps` series. The exact current query templates follow, rendered with default selectors; actual runs restrict namespace/workload/node.

### `deployment_cpu_usage`

- **Definition / derivation:** sum of container CPU counter rates, joined through pod → ReplicaSet → Deployment.
- **Unit and level:** CPU cores; Deployment.
- **Use / research question:** Locate CPU contention and integrate compute consumption.
- **Example:** 120 CPU-seconds / 60 seconds = 2 cores.
- **Direction and limitations:** no universal better direction. Sidecar CPU is included; missing owner joins omit series. More useful work can increase CPU; low CPU is not recovery.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (namespace, deployment) (rate(container_cpu_usage_seconds_total{namespace=~".+", container!="", container!="POD"}[1m]) * on (namespace, pod) group_left(replicaset) label_replace(kube_pod_owner{namespace=~".+", owner_kind="ReplicaSet"}, "replicaset", "$1", "owner_name", "(.*)") * on (namespace, replicaset) group_left(deployment) label_replace(kube_replicaset_owner{namespace=~".+", owner_kind="Deployment", owner_name=~".+"}, "deployment", "$1", "owner_name", "(.*)"))
```

### `deployment_cpu_request_utilization_percent`

- **Definition / derivation:** 100 × deployment CPU cores / summed regular-container requested CPU cores.
- **Unit and level:** % of requested CPU; Deployment.
- **Use / research question:** Assess reservation pressure and HPA/capacity decisions.
- **Example:** 0.6 / 0.4 × 100 = 150%.
- **Direction and limitations:** no universal better direction. Requests are not limits. Native sidecar usage may be in the numerator while restartable init-container requests are absent from the denominator. Values above 100% do not alone prove throttling.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
100 * (sum by (namespace, deployment) (rate(container_cpu_usage_seconds_total{namespace=~".+", container!="", container!="POD"}[1m]) * on (namespace, pod) group_left(replicaset) label_replace(kube_pod_owner{namespace=~".+", owner_kind="ReplicaSet"}, "replicaset", "$1", "owner_name", "(.*)") * on (namespace, replicaset) group_left(deployment) label_replace(kube_replicaset_owner{namespace=~".+", owner_kind="Deployment", owner_name=~".+"}, "deployment", "$1", "owner_name", "(.*)")) / sum by (namespace, deployment) (kube_pod_container_resource_requests{namespace=~".+", resource="cpu", unit="core"} * on (namespace, pod) group_left(replicaset) label_replace(kube_pod_owner{namespace=~".+", owner_kind="ReplicaSet"}, "replicaset", "$1", "owner_name", "(.*)") * on (namespace, replicaset) group_left(deployment) label_replace(kube_replicaset_owner{namespace=~".+", owner_kind="Deployment", owner_name=~".+"}, "deployment", "$1", "owner_name", "(.*)")))
```

### `deployment_memory_request_utilization_percent`

- **Definition / derivation:** 100 × summed working-set bytes / summed regular-container requested memory bytes.
- **Unit and level:** % of requested memory; Deployment.
- **Use / research question:** Assess memory reservations and investigate pressure.
- **Example:** 384 MiB / 512 MiB × 100 = 75%.
- **Direction and limitations:** no universal better direction. Working set is not an OOM limit; native sidecar reservation mismatch can inflate the ratio. Zero requests yield unavailable/nonfinite values.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
100 * (sum by (namespace, deployment) (container_memory_working_set_bytes{namespace=~".+", container!="", container!="POD"} * on (namespace, pod) group_left(replicaset) label_replace(kube_pod_owner{namespace=~".+", owner_kind="ReplicaSet"}, "replicaset", "$1", "owner_name", "(.*)") * on (namespace, replicaset) group_left(deployment) label_replace(kube_replicaset_owner{namespace=~".+", owner_kind="Deployment", owner_name=~".+"}, "deployment", "$1", "owner_name", "(.*)")) / sum by (namespace, deployment) (kube_pod_container_resource_requests{namespace=~".+", resource="memory", unit="byte"} * on (namespace, pod) group_left(replicaset) label_replace(kube_pod_owner{namespace=~".+", owner_kind="ReplicaSet"}, "replicaset", "$1", "owner_name", "(.*)") * on (namespace, replicaset) group_left(deployment) label_replace(kube_replicaset_owner{namespace=~".+", owner_kind="Deployment", owner_name=~".+"}, "deployment", "$1", "owner_name", "(.*)")))
```

### `deployment_disk_io_bytes_per_second`

- **Definition / derivation:** sum of container read and write byte counter rates with owner joins.
- **Unit and level:** bytes/s; Deployment.
- **Use / research question:** Locate storage traffic shifts.
- **Example:** 1 MB/s reads + 2 MB/s writes = 3 MB/s.
- **Direction and limitations:** no universal better direction. Throughput is not I/O latency or queue depth; caches and missing filesystem series confound interpretation.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (namespace, deployment) ((rate(container_fs_reads_bytes_total{namespace=~".+", container!="", container!="POD"}[1m]) + rate(container_fs_writes_bytes_total{namespace=~".+", container!="", container!="POD"}[1m])) * on (namespace, pod) group_left(replicaset) label_replace(kube_pod_owner{namespace=~".+", owner_kind="ReplicaSet"}, "replicaset", "$1", "owner_name", "(.*)") * on (namespace, replicaset) group_left(deployment) label_replace(kube_replicaset_owner{namespace=~".+", owner_kind="Deployment", owner_name=~".+"}, "deployment", "$1", "owner_name", "(.*)"))
```

### `deployment_network_io_bytes_per_second`

- **Definition / derivation:** sum of Istio request and response byte counter rates.
- **Unit and level:** bytes/s; Istio destination workload.
- **Use / research question:** Observe application traffic volume.
- **Example:** 10 KB/s requests + 90 KB/s responses = 100 KB/s.
- **Direction and limitations:** no universal better direction. Despite its name, this is mesh HTTP payload volume, not all NIC traffic. Lower values can mean fewer successful requests.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (destination_workload_namespace, destination_workload) (rate(istio_request_bytes_sum{reporter=~"destination", destination_workload_namespace=~".+", destination_workload=~".+"}[1m]) + rate(istio_response_bytes_sum{reporter=~"destination", destination_workload_namespace=~".+", destination_workload=~".+"}[1m]))
```

### `node_cpu_utilization_percent`

- **Definition / derivation:** 100 × (1 − average per-CPU idle fraction).
- **Unit and level:** %; Node.
- **Use / research question:** Distinguish node-wide saturation from service-local faults.
- **Example:** idle fraction 0.2 gives 80%.
- **Direction and limitations:** no universal better direction. Includes other tenants/system work; cannot identify the causal application by itself.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
100 * (1 - avg by (node) (rate(node_cpu_seconds_total{node=~".+", mode="idle"}[1m])))
```

### `node_memory_utilization_percent`

- **Definition / derivation:** 100 × (1 − MemAvailable / MemTotal).
- **Unit and level:** %; Node.
- **Use / research question:** Identify node memory pressure.
- **Example:** 2 GiB available of 8 GiB gives 75%.
- **Direction and limitations:** no universal better direction. Available memory includes reclaimability estimates; does not establish a container OOM or memory leak.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
100 * (1 - (node_memory_MemAvailable_bytes{node=~".+"} / node_memory_MemTotal_bytes{node=~".+"}))
```

### `node_disk_io_bytes_per_second`

- **Definition / derivation:** sum of read and written byte counter rates across devices.
- **Unit and level:** bytes/s; Node.
- **Use / research question:** Identify storage activity during an incident.
- **Example:** 4 MB/s read + 6 MB/s write gives 10 MB/s.
- **Direction and limitations:** no universal better direction. Logical/physical device overlap can double count; aggregate traffic is not latency or saturation.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (node) (rate(node_disk_read_bytes_total{node=~".+", device=~".+"}[1m]) + rate(node_disk_written_bytes_total{node=~".+", device=~".+"}[1m]))
```

### `node_network_io_bytes_per_second`

- **Definition / derivation:** sum receive plus transmit rates on non-loopback interfaces.
- **Unit and level:** bytes/s; Node.
- **Use / research question:** Investigate bandwidth symptoms and node concentration.
- **Example:** 2 MB/s receive + 3 MB/s transmit gives 5 MB/s.
- **Direction and limitations:** no universal better direction. Virtual interfaces may count the same packet repeatedly; packet loss and delay require other evidence.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (node) (rate(node_network_receive_bytes_total{node=~".+", device!="lo"}[1m]) + rate(node_network_transmit_bytes_total{node=~".+", device!="lo"}[1m]))
```

### `app_instance_count`

- **Definition / derivation:** kube_deployment_spec_replicas.
- **Unit and level:** desired replicas; Deployment.
- **Use / research question:** Measure scaling decisions and replica-seconds.
- **Example:** desired 6 reports 6 even if only 4 are Ready.
- **Direction and limitations:** no universal better direction. This is desired, not Ready or Available replicas. Scale-out is not verified capacity until scheduling/readiness succeeds.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
kube_deployment_spec_replicas{namespace=~".+", deployment=~".+"}
```

### `traffic_rps`

- **Definition / derivation:** sum of rates of istio_requests_total.
- **Unit and level:** requests/s; Istio destination workload.
- **Use / research question:** Check actual offered/observed traffic and interpret load changes.
- **Example:** 6000 requests in 60 seconds = 100 requests/s.
- **Direction and limitations:** no universal better direction. Includes successful and failed mesh requests. Summing all service hops overcounts client requests; do not use it as application goodput.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (destination_workload_namespace, destination_workload) (rate(istio_requests_total{reporter=~"destination", destination_workload_namespace=~".+", destination_workload=~".+"}[1m]))
```

### `response_time_p95_seconds`

- **Definition / derivation:** histogram_quantile(0.95, summed 1-minute bucket rates) / 1000.
- **Unit and level:** seconds; Istio destination workload.
- **Use / research question:** Locate slow service paths; supporting latency evidence.
- **Example:** 950 of 1000 requests within 200 ms gives approximately 0.2 s.
- **Direction and limitations:** no universal better direction. A median of service P95 values is not application P95. Mesh latency excludes some client/network failures and depends on histogram resolution.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
(histogram_quantile(0.95, sum by (le, destination_workload_namespace, destination_workload) (rate(istio_request_duration_milliseconds_bucket{reporter=~"destination", destination_workload_namespace=~".+", destination_workload=~".+"}[1m]))) / 1000)
```

### `http_5xx_rate`

- **Definition / derivation:** sum of rates of istio_requests_total with response_code matching 5.*.
- **Unit and level:** requests/s; Istio destination workload.
- **Use / research question:** Locate server-error sources.
- **Example:** 60 server errors in 60 seconds = 1 error/s.
- **Direction and limitations:** no universal better direction. Not a failure percentage. Can fall when traffic collapses; misses connection failures and non-HTTP business failures.
- **Coverage and availability:** evaluable source samples only; missing or nonfinite data stays unavailable. Old archives can support this diagnostic when its source is present; they cannot reconstruct missing collection.

```promql
sum by (destination_workload_namespace, destination_workload) (rate(istio_requests_total{reporter=~"destination", destination_workload_namespace=~".+", destination_workload=~".+", response_code=~"5.*"}[1m]))
```

### `derived_http_5xx_ratio`

An offline diagnostic derived from matching `http_5xx_rate` and `traffic_rps`
samples: error requests/s divided by total requests/s. For example, 1 / 100 =
0.01 (1%). It is not an additional required collector query, and it is not the
Locust client failure ratio. Missing numerator, unmatched samples and zero
traffic remain unavailable. Descriptive-window 5xx imputation does not apply to
this raw-evidence diagnostic.

## Semantic rubric: ten criteria

Source: `resources/rubric.json`; final results come from `sessions/rca_session.json` and `sessions/remediation_run.json`. Succeeded and failed jobs with non-empty final result objects are semantically judged. Running and result-less jobs are not. Every criterion has ordered classes scored 0, 0.25, 0.5, 0.75, 1; higher means stronger rubric alignment. Python computes scores and weights; the model assigns classes. Missing result/judge failure is unevaluable, not zero. The unit is the final job output completed within a recorded chaos interval. Outputs outside that interval or with missing completion timestamps are not graded. Old and new final outputs are supported; independently referenced observations are normally available only in new exports.

### `root_cause_correctness` (rca)

Measures whether the agent correctly identifies the production-observable incident condition and affected component described by the ground truth.

- **Role / usefulness:** primary diagnostic. Can the system identify the observable fault mechanism?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.3 × criterion score.
- **Example:** the 0.75 class contributes 0.3 × 0.75 = 0.225 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Ground truth can omit incidental faults; corroborate expected fault potency.
- **Classes:** INCORRECT=0.0; MOSTLY_INCORRECT=0.25; PARTIALLY_CORRECT=0.5; MOSTLY_CORRECT=0.75; CORRECT=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `causal_reasoning_quality` (rca)

Measures whether the agent provides a technically plausible and coherent causal explanation connecting the identified root cause to the observed symptoms.

- **Role / usefulness:** secondary qualitative. Does the explanation connect mechanism to symptoms?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.25 × criterion score.
- **Example:** the 0.75 class contributes 0.25 × 0.75 = 0.1875 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Plausible prose is not proof of causality.
- **Classes:** NO_CAUSAL_REASONING=0.0; WEAK=0.25; PLAUSIBLE=0.5; STRONG=0.75; COMPELLING=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `evidence_grounding` (rca)

Measures the extent to which the agent's diagnosis and supporting claims are grounded in the telemetry, observations, logs, metrics, traces, or other evidence available during the incident.

- **Role / usefulness:** supporting. Are diagnosis claims supported by referenced observations?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.2 × criterion score.
- **Example:** the 0.75 class contributes 0.2 × 0.75 = 0.15 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Without observations this is reported evidence quality, not factual verification.
- **Classes:** UNGROUNDED=0.0; WEAKLY_GROUNDED=0.25; PARTIALLY_GROUNDED=0.5; WELL_GROUNDED=0.75; FULLY_GROUNDED=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `localization_accuracy` (rca)

Measures how accurately and precisely the agent identifies the location of the originating fault within the system, such as the affected node, service, deployment, pod, or resource.

- **Role / usefulness:** primary diagnostic. Can it identify the originating workload/node and affected scope?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.15 × criterion score.
- **Example:** the 0.75 class contributes 0.15 × 0.75 = 0.1125 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Do not demand pod-level specificity unsupported by observations.
- **Classes:** WRONG=0.0; BROADLY_WRONG=0.25; PARTIAL=0.5; MOSTLY_PRECISE=0.75; PRECISE=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `diagnostic_completeness` (rca)

Measures whether the RCA sufficiently explains the important symptoms and observations associated with the incident and connects them to the identified root cause.

- **Role / usefulness:** secondary qualitative. Does the explanation cover important symptoms?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.1 × criterion score.
- **Example:** the 0.75 class contributes 0.1 × 0.75 = 0.075 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Can favor verbosity and overlap with causal reasoning; irrelevant details earn no credit.
- **Classes:** INCOMPLETE=0.0; LIMITED=0.25; PARTIAL=0.5; MOSTLY_COMPLETE=0.75; COMPLETE=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `remediation_correctness` (remediation)

Measures whether the proposed remediation appropriately addresses the identified or ground-truth root cause and is expected to mitigate or resolve the incident.

- **Role / usefulness:** supporting semantic. Is the action appropriate for the fault?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.3 × criterion score.
- **Example:** the 0.75 class contributes 0.3 × 0.75 = 0.225 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** An appropriate plan can be unexecuted or ineffective in practice.
- **Classes:** INCORRECT=0.0; MOSTLY_INCORRECT=0.25; PARTIALLY_CORRECT=0.5; MOSTLY_CORRECT=0.75; CORRECT=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `technical_feasibility` (remediation)

Measures whether the proposed remediation can realistically be executed in the given Kubernetes/cloud-native environment using the available system capabilities and operational mechanisms.

- **Role / usefulness:** supporting semantic. Could this action execute within the available Kubernetes capabilities?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.2 × criterion score.
- **Example:** the 0.75 class contributes 0.2 × 0.75 = 0.15 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Reported feasibility does not prove admission, scheduling or rollout completion.
- **Classes:** INFEASIBLE=0.0; MOSTLY_INFEASIBLE=0.25; PARTIALLY_FEASIBLE=0.5; MOSTLY_FEASIBLE=0.75; FEASIBLE=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `risk_and_safety` (remediation)

Measures whether the remediation minimizes unnecessary operational risk, limits potential blast radius, and avoids actions that could introduce additional service disruption.

- **Role / usefulness:** supporting semantic. Is the proposed blast radius justified?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.2 × criterion score.
- **Example:** the 0.75 class contributes 0.2 × 0.75 = 0.15 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** This score does not replace the independent hard safety gate.
- **Classes:** HIGH_RISK=0.0; RISKY=0.25; MODERATE_RISK=0.5; LOW_RISK=0.75; SAFE=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `evidence_alignment` (remediation)

Measures whether the selected remediation logically follows from the observed evidence and diagnosed root cause rather than relying on unsupported assumptions.

- **Role / usefulness:** supporting. Does the selected action follow from the observed incident?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.15 × criterion score.
- **Example:** the 0.75 class contributes 0.15 × 0.75 = 0.1125 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Generally valid actions may be unjustified; no observations means reported alignment only.
- **Classes:** UNALIGNED=0.0; WEAKLY_ALIGNED=0.25; PARTIALLY_ALIGNED=0.5; WELL_ALIGNED=0.75; FULLY_ALIGNED=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

### `remediation_completeness` (remediation)

Measures whether the proposed remediation provides a sufficiently complete response to the incident, including the actions necessary to mitigate or resolve the problem and, when appropriate, verification of recovery.

- **Role / usefulness:** secondary qualitative. Are corrective and verification steps sufficient?
- **Source / derivation:** judge classification → class score from `rubric.json`; weighted contribution = 0.15 × criterion score.
- **Example:** the 0.75 class contributes 0.15 × 0.75 = 0.1125 to the kind's weighted score.
- **Unit / direction:** score in [0,1], higher is more aligned with the criterion; a job output is the measurement unit.
- **Limitations:** Claims of verification must be checked against independent recovery measurements.
- **Classes:** INCOMPLETE=0.0; LIMITED=0.25; PARTIAL=0.5; MOSTLY_COMPLETE=0.75; COMPLETE=1.0.
- **Coverage / availability:** requires a final result and successful classification; historical outputs remain usable, but absent factual evidence cannot be recovered from eloquent claims.

## Descriptive baseline and sliding-window metrics

| Metric | Calculation and unit | Interpretation |
| --- | --- | --- |
| Client mean response time estimate | `(N2 × M2 − N1 × M1) / (N2 − N1)`, converting cumulative Locust means from ms to seconds | Available in independent comparisons; not in the paired scenario table |
| Service P95 time average | Time-weighted average of archived `response_time_p95_seconds` samples; seconds | Average of rolling workload percentiles, **not** the pooled P95 of requests in the selected window |
| HTTP 5xx time average | Time-weighted average of archived `http_5xx_rate`; requests/s | Error rate, **not a percentage**; a traffic drop can lower it |
| Absolute change | Selected value minus baseline | Same units as the metric |
| Relative change | `(selected − baseline) / baseline` | CSV `relative_change` is a fraction; Markdown shows percent. Null when baseline is zero |
| Coverage | Supported seconds / interval seconds | At least 90% is required for an eligible value |

Client means use `Total Request Count` and `Total Average Response Time` in
`*_stats_history.csv`. They assume counted requests have response times; CSV
rounding and failures without timings limit accuracy. Counter resets invalidate
measurements. Cumulative history P95 cannot be converted to interval client P95.

Complete windows advance by the recorded Prometheus scrape step within each
recorded chaos step, ending before cleanup. They never bridge idle steps.
A one-hour interval with five-minute windows and a 15-second step has 221
candidate locations. Ties choose the earliest location. These are scheduled
fault intervals, not proof that injection was continuously active.

Service time averages use right-endpoint integration: a sample at `t` supports
at most one scrape step ending at `t`. At least two finite nonnegative samples
and 90% coverage are required. Gaps are not interpolated. Rolling source queries
can contain observations from before the selected boundary.

The independent comparison requires an evaluable baseline before selecting a
metric's best window. The paired table can retain covered chaos windows
even when its trimmed baseline is unavailable. Paired windows require both P95
and 5xx coverage. Defaults are `--table-workload front-end` and
`--table-max-5xx-rate 0.5`; use `--table-namespace` when the workload is ambiguous.

### Explicit HTTP 5xx imputation

For descriptive comparisons only, an absent 5xx sample in a successful archived
result matrix is filled with zero at a matching finite traffic timestamp for
the same namespace/workload. This includes an absent workload series. It is an
analysis assumption, not an observed zero. Missing/failed query files, explicit
nonfinite samples, traffic gaps, latency and semantic scores are not filled.

`window_comparison.csv` records `missing_value_policy`,
`baseline_imputed_samples`, and `window_imputed_samples`. The scenario table
records baseline/best imputed-sample counts. Per-run JSON retains policy
and coverage. Recovery calculations continue to use raw evidence.

## Archive recovery proxy: per-run JSON

Read `research.operational` in `runs/<run>/grade.json`. These measurements are
separate from rubric scores and descriptive windows. Defaults come from
[`evaluation-policy.json`](../resources/evaluation-policy.json).

| Measurement | Definition |
| --- | --- |
| Client failure ratio | Difference in cumulative failures / difference in cumulative attempts; fraction |
| Successful client throughput | `(attempted − failed) / measured seconds`; requests/s |
| Measured failed requests | Incident counter increase, retained in `harm.failed`, with measured endpoints and coverage |
| Whole-run client mean/P95 | Omitted from chaos-only metrics because cumulative summaries include baseline and post-chaos data |
| Service reference | Per-service time median of baseline P95 and traffic for every baseline-active service |
| Healthy bin | Client failure ratio ≤baseline +0.001; successful throughput ≥90% baseline; every service's max P95 ≤120% baseline and min traffic ≥90% baseline |
| Recovery streak | 120 consecutive healthy seconds after a qualifying degraded bin; default bins are 30 seconds |
| `proxy_recovery_seconds` | Start of qualifying streak minus recorded schedule start; confirmation occurs at the streak's end |

The last-five-minute baseline must have completed, pass any recorded health
assessment, have client failure ratio ≤1%, and satisfy coverage/request rules.
Client bins need at least 100 requests and 90% coverage. Service checks need at
least two samples per bin; archive scrape step must be ≤15 seconds. Missing
bins break recovery streaks. The observation deadline is recorded metrics end.
Full algorithm and exclusions are in [methodology.md](methodology.md).

| Operational status | Meaning |
| --- | --- |
| `proxy_recovered` | Sustained recovery under the archive proxy was observed |
| `proxy_unresolved` | No qualifying recovery streak before the observation deadline |
| `no_observed_degradation` | No qualifying degraded interval; do not interpret as zero-time recovery |
| `not_evaluable` | Required boundaries, samples or coverage are unavailable |
| `invalid` | An applicable validity check failed, such as unhealthy baseline or failed/interrupted run |

The first failing evidence check determines the status/reason: an early startup
failure with no timestamps can be `not_evaluable`. Inspect source run status and
metadata as well. `proxy_recovered` does not prove agent causality, independent
safety, or recovery while a fault was physically active. Strict `recovered`,
`recovery_seconds`, and `active_fault_recovery` remain unknown for ordinary
archives. Schedule-phase labels describe timing only.

## Semantic scores and lifecycle status

Weighted rubric totals range from 0 to 1. Remediation's final total is
`max(0, rubric_score − penalty_total)`; RCA has no penalties. Alignment uses
root-cause/remediation correctness ≥0.75, independently of penalties.
Scenario-table score maxima and means include scored succeeded **and failed**
jobs. Missing scores are excluded, not zero. Session counts include all exported
jobs, including running and result-less jobs; they are not scored denominators.

Current RemediatorAgent `succeeded` means it produced nonempty final output;
that output may report a failed, skipped or unverified action. Historical
statuses retain their original meaning. Grader preserves status and `is_failed`
and judges final result content; it does not relabel archived jobs.

Top-level `graded` means semantic input processing completed, not that a scenario
ran successfully or recovered. Empty session arrays are valid but do not prove
absence of anomalies: startup failures, interruption before activation, no-agent
runs, and export problems must be distinguished using run evidence.

Legacy per-job `metric_outcome` and `final_grade` columns are retained as
`not_evaluable`: recovery is now assessed once per incident, in
`research.operational`. They are not indicators of a failed semantic judge.

## Optional evidence and retired reports

Portable `evidence/` inputs can support verified actions/safety, client histogram
recovery, detector matching, resource integrals and model usage/cost. Availability
and measurement bases must be checked per field. They are not required for normal
archive grading; see [evidence-contract.md](evidence-contract.md).

The normal CLI no longer emits `incidents.csv`, `incidents.json`,
`paper_metrics.csv`, `research_summary.*`, or `scenario_table.md/json`.
Historical files and helper functions can still exist; they are not current
CLI outputs. Do not treat their old counts as the current campaign's results.


### Chaos-only grading scope

Grading uses `scheduled-chaos-only-v1`: each non-idle step starts at its recorded
`active_started_at` and ends at the earlier of `cleanup_started_at` or start plus
its recorded `duration` (seconds). A one-hour step is therefore capped at 60
minutes; earlier cleanup shortens it. Both actual start and cleanup timestamps
are required; planned duration alone never proves the step ran. Missing or invalid
boundaries are unevaluable. Performance measurements also stop at telemetry end.

Baseline telemetry remains a reference for comparisons. Chaos metrics, recovery
streaks, diagnostic summaries and resource integrals exclude baseline, idle gaps,
cleanup and post-chaos observation. Complete windows must fit inside one chaos
interval. Archived Prometheus rolling samples may still contain lookback data
from before their timestamp; raw request-level intervals cannot be reconstructed.

RCA/remediation scores and scenario session counts include only outputs whose
`completed_at` falls in `[chaos_start, chaos_end)`. Outputs completing exactly at
the end are excluded. Excluded jobs retain their original lifecycle status and
an explicit `time_scope` reason in `grade.json`; the judge is not called for them.
The notebook applies the same filter to historical grades and exposes excluded
session counts. Historical grade files and judge caches are not rewritten by
notebook execution. Whole-run cumulative client mean/P95 summaries are omitted
from chaos-only metrics.
