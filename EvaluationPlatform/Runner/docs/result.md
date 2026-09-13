# Evaluation results

This document describes what an Evaluation run records, which metrics are
extracted, how derived values are calculated, and how to decide whether a run
is usable. The run directory is the durable unit of evidence. Keep the whole
directory: a chart or summary row alone is not enough to reproduce or explain
a result.

## Result lifecycle

By default, a run is written to
`results/<timestamp>-<scenario>-<unique suffix>/`. An explicit `--output-dir` replaces
that path. `metadata.json` is created with `status: running`, updated after
each phase and chaos step, and finalized even when the run fails or is
interrupted. The `export-sessions` post-run hook then adds Orchestrator HTTP exports under `sessions/`.

The typical result tree is:

```text
<run>/
├── run-status.json
├── run-context.json
├── resolved-scenario.json
├── hooks.json
├── hooks/
├── metadata.json
├── application-install.json
├── inputs/
│   ├── scenario.json
│   ├── chaos/<reference>.yaml
│   └── placement/{source/,rendered.yaml}
├── loadgenerator/
│   ├── locustfile.py
│   ├── <shape>.html
│   ├── <shape>.log
│   ├── <shape>.stdout
│   ├── <shape>_stats.csv
│   ├── <shape>_stats_history.csv
│   ├── <shape>_failures.csv
│   └── <shape>_exceptions.csv
├── metrics/
│   ├── metrics.json
│   └── <metric-family>.json
├── snapshots/
│   ├── baseline-before-load/
│   └── final/
├── injector/<step>/<schedule>/
├── commands/<phase>/
└── sessions/
    ├── anomaly.json
    ├── rca_session.json
    ├── remediation_run.json
    ├── remediation_session.json
    ├── learning_session.json
    └── workflow.json
```

Some files are absent when their producer never started or failed. This is
evidence about the run, not a reason to silently substitute data from another
run.

## Run metadata and exact inputs

`metadata.json` uses schema version 2 and is the index for a result. It records:

- run start and finish times, final status, namespace, application, command
  arguments, baseline and grace periods, and whether agents were enabled;
- the normalized scenario and its ordered steps;
- the placement reference, rendered-manifest SHA-256, node preflight,
  observed pod-to-node placement, and observed placement fingerprint;
- archived chaos definitions and hashes;
- load-generator command, duration, and return code;
- phase results, command results, snapshots, chaos active windows, cleanup
  verification, and Prometheus collection metadata;
- errors raised by execution or best-effort finalization.

Sensitive database arguments are redacted before metadata is written. The
files under `inputs/` are the exact scenario, Chaos Mesh resources, and
placement used by the run. Use these archived inputs—not the repository's
current versions—when interpreting an old result.

## Prometheus time-series metrics

The runner queries the complete load interval with Prometheus `query_range`.
The range begins when the load phase starts and ends when scenario execution
finishes (or at finalization after an early failure). The fixed defaults are a
15-second sample step and a 1-minute rate window. `metrics/metrics.json`
records the namespace, range, step, rate window, exact PromQL, request URL,
success flag, output filename, and any per-query error.

Each `<metric-family>.json` retains the unmodified Prometheus HTTP response.
Series identity is normally `deployment`, `destination_workload`, or `node`.
The 13 extracted families are:

| File / family | Unit | Meaning |
| --- | --- | --- |
| `deployment_cpu_usage` | CPU cores | Container CPU usage rate, summed to Deployment through pod, ReplicaSet, and Deployment ownership. |
| `deployment_cpu_request_utilization_percent` | percent | Deployment CPU usage divided by requested CPU. Values above 100% mean usage exceeds requests, not necessarily limits. |
| `deployment_memory_request_utilization_percent` | percent | Working-set bytes divided by requested memory for each Deployment. |
| `deployment_disk_io_bytes_per_second` | bytes/s | Container filesystem read plus write rate, summed per Deployment. |
| `deployment_network_io_bytes_per_second` | bytes/s | Istio request plus response byte rate for each destination workload. |
| `node_cpu_utilization_percent` | percent | `100 * (1 - average idle CPU rate)` per node. |
| `node_memory_utilization_percent` | percent | `100 * (1 - MemAvailable / MemTotal)` per node. |
| `node_disk_io_bytes_per_second` | bytes/s | Node disk read plus write rate across devices. |
| `node_network_io_bytes_per_second` | bytes/s | Node receive plus transmit rate, excluding loopback. |
| `app_instance_count` | replicas | Desired replicas from `kube_deployment_spec_replicas`, not the count of Ready pods. |
| `traffic_rps` | requests/s | Istio request rate grouped by destination workload. |
| `response_time_p95_seconds` | seconds | Istio destination-side P95 request duration; histogram milliseconds are converted to seconds. |
| `http_5xx_rate` | responses/s | Istio destination-side rate of responses whose code starts with 5. |

The Deployment resource metrics depend on cAdvisor and kube-state-metrics
ownership series. Node metrics depend on node-exporter. Traffic, latency,
5xx, and workload network metrics depend on Istio telemetry and use the
destination reporter. A successful HTTP query can legitimately contain no
series when the required exporter, mesh telemetry, labels, or traffic are
absent; check both `ok` and the response's `data.result`.

## Load-generator metrics

Locust writes its native HTML, logs, exceptions, failures, aggregate stats,
and stats history under `loadgenerator/`. Derived step summaries use only the
`Aggregated` rows of the first `*_stats_history.csv` file:

- `request_count`: cumulative requests at window end minus the count before
  the window;
- `failure_count`: the corresponding cumulative-failure difference;
- `failure_pct`: `100 * failure_count / request_count`;
- `avg_response_ms`: the request-count-weighted difference of Locust's
  cumulative average response time;
- `locust_avg_rps`: mean of Locust `Requests/s` samples in the window.

`avg_response_ms` and `failure_pct` in reporting come from Locust. Prometheus
P95, RPS, and 5xx values come from Istio, so they measure a different boundary
and should not be expected to match exactly.

## Point-in-time snapshots

Snapshots are taken before load begins and during finalization. Each snapshot
contains `snapshot.json`, stdout/stderr for every command, and four optional
instant Prometheus responses. Kubernetes commands capture:

- pods (wide and full JSON), Deployments (wide and full JSON), HPAs, Services,
  namespace events, and cluster nodes;
- `kubectl top` for pods and nodes;
- pod phase and restart counts;
- per-container CPU/memory requests and limits.

Instant Prometheus checks capture `up`, five-minute pod CPU rate, pod memory
working set, and pod restart count. The final snapshot is post-cleanup and is
useful for finding collateral or persistent state. Command return codes and
stderr must be checked before treating a snapshot as complete.

## Chaos, commands, and session evidence

`injector/` and `commands/` preserve Schedule apply/delete/wait operations,
agent scaling, placement checks, port-forwarding, and startup/final cleanup.
The matching `metadata.chaos_steps` entries provide each step's start, active,
finish, status, Schedule types/actions, and cleanup outcome. These timestamps
define reporting windows and the visual timeline.

Postrun exports the agent database as JSON:

- `anomaly.json`: detector events and ingestion data;
- `rca_session.json`: RCA jobs, timestamps, status, and final result;
- `remediation_run.json`: remediation jobs and final result;
- `remediation_session.json`: remediation audit/tool context;
- `learning_session.json`: learning jobs and generated lessons;
- `workflow.json`: end-to-end workflow state and relationships.

The exports are observational copies. Their presence does not prove that a job
succeeded; inspect record status, timestamps, and final result fields. Postrun
requires the Orchestrator control-token environment variable, so a completed testbed run can still have missing
session exports if postrun fails.

## Derived step reports

The reporting pipeline reads schema-version-2 runs and emits:

- `chaos-step-summary.csv`: one row per run and chaos step;
- `chaos-step-agent-comparison.csv`: paired agent versus non-agent values and
  percentage improvements.

For each active step it derives average and peak total Deployment CPU,
Locust average response time, average and peak Istio P95, average total Istio
RPS and 5xx rate, Locust failure percentage, and average desired replicas.
Values from multiple series are summed at each timestamp before averaging or
taking a peak where appropriate.

Comparison pairs require the same application, scenario, placement reference,
placement-definition fingerprint, step index/name, and chaos set. For
lower-is-better metrics, improvement is
`100 * (non_agent - agent) / non_agent`; for RPS and instance count the sign is
reversed. A zero non-agent denominator produces no percentage value. These
figures describe association within a matched window; they do not by
themselves prove that remediation caused the change.

## Graded results

The grader is a separate read-only consumer. It evaluates every succeeded RCA
or remediation job with a non-empty final `result` against the scenario's
production-style manual ground truth. The semantic rubric judge does not
receive archived chaos manifests, tool traces, requests, raw model output,
reasoning, anomaly rows, or learning records. Manifests remain validated and
retained for provenance and are supplied only to the separate remediation
penalty judge. Rubric classes are converted to weighted 0–1 scores;
remediation can also receive scenario-specific penalties.

The shared [scenario grading policy](../../Grader/grader/scenario-policy.md) defines the
audited fault-family expectations, partial-credit treatment, simulation-wide
exclusions, and penalty weights used by all 51 scenario-specific ground truths.

For each completed remediation, the grader compares five-minute Prometheus
windows immediately before and after `completed_at`. It evaluates only
`response_time_p95_seconds` and `http_5xx_rate`; the other 11 collected
families are ignored by grading and remain available for reporting and
visualization. It takes each series' median and then the median across series.
Both evaluated metrics are lower-is-better at the default inclusive 15%
threshold.

A metric outcome is `good` only when neither evaluated family worsens and at
least one improves. It is `not_evaluable` when either family lacks samples in
one of the windows. The final remediation grade is `good` only when semantic
alignment and the metric outcome are both good.

The grader writes per-run `grade.json`, `report.md`, and judge cache files,
plus aggregate `summary.csv`, RCA/remediation rubric score CSVs, and
`grades/report.md`. Each Markdown report starts with an RCA rubric-score table
and a single remediation table combining rubric scores with the before/after
values, percentage changes, and assessments for response-time P95 and HTTP 5xx
rate. See [`../grader/README.md`](../../Grader/grader/README.md) for the complete rubric,
penalty, cache, and output contracts.

## Visualization outputs

The visualizer reads the raw metric files and lifecycle/session timestamps. It
can produce metric-only plots, metrics aligned with lifecycle lanes, and a
timeline-only plot with `events.csv`. Elapsed minute zero is
`metadata.started_at`; when absent, the earliest valid event is used and a
warning is recorded. Visualization does no grading and does not contact the
cluster or model. See [`../visualizer/README.md`](../../Grader/visualizer/README.md).

## Validity checklist

Before comparing or publishing a result, verify:

1. `metadata.status` and every phase/chaos-step status are expected.
2. Final chaos cleanup succeeded and no finalization error is recorded.
3. The archived scenario, chaos, and placement inputs are present and hashes
   agree with metadata.
4. Agent and control runs have matching application, scenario, placement
   definition, load shape, baseline, and complete load windows.
5. Prometheus queries have `ok: true` and contain the expected series; Locust
   history spans the windows being summarized.
6. Snapshot commands succeeded and baseline placement invariants held.
7. Session rows have valid statuses and timestamps before latency or grading
   conclusions are drawn.

A run is not valid for causal comparison when cleanup failed, exact inputs are
missing, placement-definition fingerprints differ, baseline invariants failed,
or the workload/application window is incomplete. Observed pod-to-node
fingerprints are still useful diagnostic evidence and can differ under soft
topology spreading.
