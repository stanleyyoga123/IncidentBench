# Simple independent RCA and remediation grader

`grader` is an offline grading path for archived Evaluation runs. It does not
inspect agent reasoning or tool calls, or contact a Kubernetes cluster.

## Run it

From `Evaluation/`:

```bash
PYTHONPATH=. python -m grader --input results --output grades
```

The semantic judge defaults to the local OpenAI-compatible vLLM endpoint at
`http://localhost:8000/v1` and model `Qwen/Qwen3.6-35B-A3B`. The environment
variables `JUDGE_URL`, `JUDGE_MODEL`, and `JUDGE_TOKEN` remain supported.

```bash
PYTHONPATH=. python -m grader \
  --input results \
  --output grades \
  --ground-truth grader/ground_truth \
  --rubric grader/rubric.json \
  --penalties grader/penalties \
  --base-url http://localhost:8000/v1 \
  --model Qwen/Qwen3.6-35B-A3B \
  --token EMPTY \
  --judge-timeout-seconds 600 \
  --judge-max-tokens 8192 \
  --window-minutes 5 \
  --threshold 0.15 \
  --verbose
```

Use `--refresh-judge` to ignore reusable judge checkpoints. Tokens are passed
to the client only and are never written to grader artifacts.

Every CLI run writes a fresh, DEBUG-level `grades/grader.log`. It records run
discovery, validation and skip reasons, job lifecycle status, cache hits and
hashes, judge call outcomes, metric-family medians and assessments, final
grades, and artifact locations. Normal console output is concise; `--verbose`
also displays DEBUG events on the console. Logs never include the judge token,
prompts, ground-truth or manifest bodies, final result contents, raw output,
reasoning, tool calls, or learning data.

## Required archived inputs

Each run is discovered through `metadata.json` and must contain:

- `inputs/scenario.json`, including the scenario name and chaos references;
- every referenced `inputs/chaos/<reference>.yaml` manifest;
- a matching manually maintained
  `grader/ground_truth/<scenario-name>.md` file with non-empty `## RCA` and
  `## Recommended remediation` sections;
- the scoring rubric at `grader/rubric.json`, or another file passed with
  `--rubric`;
- optional scenario penalty arrays under `grader/penalties/<scenario-name>.json`,
  or another directory passed with `--penalties`;
- optional `sessions/rca_session.json` and
  `sessions/remediation_run.json` exports;
- Prometheus query-range JSON in `metrics/` for metric grading.

Ground truth is never generated or overwritten. A missing ground-truth file,
archived scenario, or archived chaos manifest marks only that run `ungraded`;
other runs continue.

## Rubric classification

Every exported job is reported independently. Only a succeeded job with a
non-empty final `result` is sent to the judge.

`grader/rubric.json` is the source of truth for criterion ids, class labels,
definitions, scores, and weights. The judge only assigns a class to each
criterion. Python converts those classes into 0–1 scores and the weighted
overall score. Editing the JSON changes both the prompt and the numeric scale
without code changes.

The RCA payload contains exactly the scenario name, RCA ground truth,
normalized archived chaos manifests, and `rca_job.result`. The remediation
payload uses the remediation ground-truth section and `remediation_job.result`.
Evidence-grounding and causal-reasoning are judged from claims inside that
final result against ground truth and the injected manifests. Tool traces are
not supplied.

Requests, raw model output, anomalies, tool calls, reasoning, session traces,
learning records, and remediation-session exports are not read. The judge runs
at temperature zero with a strict per-criterion response object:

```json
{
  "root_cause_correctness": {"class": "MOSTLY_CORRECT", "reason": "concise evidence-specific reason"}
}
```

Allowed `class` values are the enums from `rubric.json`. Each reason is at most
500 characters. Failed, running, and result-less jobs, plus individual judge
failures, remain visible as `not_evaluable`.

Alignment is derived in code from the first criterion of that kind
(root-cause correctness or remediation correctness). A job is `aligned` when
that criterion's score is at least 0.75, otherwise `not_aligned`. Alignment
does not use penalty results.

## Remediation penalties

Remediation-only. After rubric classification, if
`grader/penalties/<scenario-name>.json` exists and is non-empty, the judge
makes a second structured call. Each file is a JSON array:

```json
[
  {"criteria": "Uncordon or return worker-node-3 to service while the injected network delay remains.", "penalty": 0.5}
]
```

The judge returns only whether each criterion `applied`. Python subtracts the
configured amounts from the weighted rubric score and floors at 0:

`overall_score = max(0, rubric_score - penalty_total)`

A missing file means no penalties and no second call. RCA never reads these
files. Penalty checkpoints are cached separately with the penalty-file hash, so
editing a penalty JSON does not redo rubric classifications.

Each successful classification is cached immediately and atomically by SHA-256
over the prompt version, rubric hash, model, job kind, selected ground truth,
normalized manifests, and final result JSON. Editing `rubric.json` therefore
invalidates old rubric checkpoints. `JUDGE_MAX_TOKENS` or `--judge-max-tokens`
controls the response allowance; the 8,192-token default accommodates local
reasoning models.

## Five-minute metric comparison

For each succeeded remediation with a result, `completed_at` is the anchor.
The before window is `[completed_at - 5 minutes, completed_at)` and the after
window is `[completed_at, completed_at + 5 minutes]`. The duration is
configurable. The grader computes the median of valid samples in each window
for every Prometheus series, followed by a median across evaluable series for
the family.

All 13 collected families are evaluated:

| Policy | Metric families |
| --- | --- |
| Lower is better | `response_time_p95_seconds`, `http_5xx_rate`, `deployment_cpu_usage`, `deployment_cpu_request_utilization_percent`, `deployment_memory_request_utilization_percent`, `node_cpu_utilization_percent`, `node_memory_utilization_percent` |
| Higher is better | `traffic_rps` |
| Stability is better | `app_instance_count`, `deployment_disk_io_bytes_per_second`, `deployment_network_io_bytes_per_second`, `node_disk_io_bytes_per_second`, `node_network_io_bytes_per_second` |

At the default inclusive 15% boundary, an expected-direction change is
`improved`, an opposite-direction change is `worsened`, and a smaller change is
`stable`. Stability metrics are `worsened` by an absolute change of 15% or
more. Zero-to-zero is stable; zero-to-positive and positive-to-zero use the
family direction. Missing or nonnumeric windows are `not_evaluable`.

The core-health gate comprises response-time P95, 5xx rate, traffic RPS, and
instance count. The metric outcome is:

- `good` when no core family worsens and at least one evaluable family improves;
- `not_good` when a core family worsens or no family measurably improves;
- `not_evaluable` when any required core family lacks both windows.

The final remediation grade is `good` only when derived alignment is `aligned`
and the metric outcome is `good`. An evaluable mismatch is `not_good`; an
unevaluable semantic or metric input makes the final grade `not_evaluable`.

## Outputs

For each run, the grader writes:

- `grades/runs/<run>/grade.json`: normalized grading inputs, each final job
  result, rubric classifications and scores, derived alignment, every metric
  family and series, and final grades;
- `grades/runs/<run>/report.md`: concise RCA, remediation, criterion, and
  family summaries;
- `grades/runs/<run>/judge-cache.json`: hash-keyed classification checkpoints.

It also writes `grades/summary.csv`, one row per RCA/remediation job;
`grades/rca_rubric_score.csv` and `grades/remediation_rubric_score.csv`, one
row per session with each criterion class/score plus `overall_score`;
remediation score CSV also has `rubric_score` and `penalty_total`; and
`grades/report.md`, with aggregate counts, mean overall and per-criterion
scores, per-session rubric tables, applied penalties, skipped runs, and
non-evaluable jobs. These output files are deterministic apart from newly
returned judge reasons.

The per-run JSON has this stable top-level shape (nested manifests, results,
and metric series are retained in full):

```json
{
  "schema_version": 1,
  "run": "run-folder-name",
  "scenario": "scenario-name",
  "status": "graded",
  "reason": null,
  "inputs": {
    "scenario": {},
    "ground_truth": {"rca": "...", "remediation": "..."},
    "chaos_manifests": []
  },
  "configuration": {},
  "rca_jobs": [],
  "remediation_jobs": []
}
```

Each RCA job contains identifiers, lifecycle timestamps, the final result, a
`rubric` object with `overall_score` and per-criterion class/score/reason, and
a derived alignment record. Each remediation job additionally contains
`metrics`, `final_grade`, `rubric_score`, `penalty_total`, and applied penalty
items. `overall_score` is the penalized session total. The flat summary CSV
columns are `run`, `scenario`, `kind`, `job_id`, `workflow_id`, `status`,
`alignment`, `overall_score`, `metric_outcome`, `final_grade`, and `reason`.
Each rubric score CSV adds `<criterion>_class` and `<criterion>` columns plus
`overall_score`. Remediation score CSV also adds `rubric_score` and
`penalty_total`. An ungraded run retains the same top-level shape with empty
job lists and an explicit reason.
