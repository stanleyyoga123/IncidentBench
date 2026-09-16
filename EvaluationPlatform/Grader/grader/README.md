# Simple independent RCA and remediation grader

`grader` is an offline grading path for archived Evaluation runs. It does not inspect private agent reasoning or contact a Kubernetes cluster. It consumes portable observations and action evidence when available.

See [scenario-policy.md](../resources/scenario-policy.md) for the audited fault-family
expectations, partial-credit rules, universal simulation exclusions, and
penalty weights applied across all 51 scenarios.

## Run it

From `EvaluationPlatform/Grader/`:

```bash
PYTHONPATH=. python -m grader --input ../Runner/results --output grades/research-v2
```

The semantic judge defaults to the local OpenAI-compatible vLLM endpoint at
`http://localhost:8000/v1` and model `Qwen/Qwen3.6-35B-A3B`. The environment
variables `JUDGE_URL`, `JUDGE_MODEL`, and `JUDGE_TOKEN` remain supported.
Run folders are graded concurrently, with five workers by default. Set
`--concurrency` or `GRADER_CONCURRENCY` to tune the number of simultaneous
judge requests for the available model-server capacity. Jobs within each run
remain sequential.

The local `grade.sh` hard-codes its arguments and does not forward extra flags.
Use direct module invocations for configurable runs:

```bash
python -m grader --input results/sock-shop-1 --output grades/new-assessment --concurrency 10
```

```bash
PYTHONPATH=. python -m grader \
  --input results \
  --output grades \
  --ground-truth resources/ground_truth \
  --rubric resources/rubric.json \
  --penalties resources/penalties \
  --base-url http://localhost:8000/v1 \
  --model Qwen/Qwen3.6-35B-A3B \
  --token EMPTY \
  --judge-timeout-seconds 600 \
  --judge-max-tokens 8192 \
  --concurrency 5 \
  --evaluation-policy resources/evaluation-policy.json \
  --verbose
```

Use `--refresh-judge` to ignore reusable judge checkpoints. Tokens are passed
to the client only and are never written to grader artifacts.

Every CLI run writes a fresh, DEBUG-level `grades/logs/grader.log`. It records run
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
  `resources/ground_truth/<scenario-name>.md` file with non-empty `## RCA` and
  `## Recommended remediation` sections;
- the scoring rubric at `resources/rubric.json`, or another file passed with
  `--rubric`;
- optional scenario penalty arrays under `resources/penalties/<scenario-name>.json`,
  or another directory passed with `--penalties`;
- optional `sessions/rca_session.json` and
  `sessions/remediation_run.json` exports;
- Prometheus query-range JSON in `metrics/` for metric grading.

Ground truth is never generated or overwritten. A missing ground-truth file,
archived scenario, or archived chaos manifest marks only that run `ungraded`;
other runs continue. Archived manifests remain required for reproducibility,
input validation, and remediation-penalty judging, but are not supplied to the
normal RCA or remediation rubric judge.

## Rubric classification

Every exported job is reported independently. Succeeded and failed jobs with a
non-empty final `result` are sent to the judge. The archived lifecycle status is
preserved independently of semantic quality. Running jobs remain non-evaluable.

`resources/rubric.json` is the source of truth for criterion ids, class labels,
definitions, scores, and weights. The judge only assigns a class to each
criterion. Python converts those classes into 0–1 scores and the weighted
overall score. Editing the JSON changes both the prompt and the numeric scale
without code changes.

Both semantic payloads contain scenario name, ground truth, final result, and bounded portable observations when available. Evidence claims are cross-checked against those observations; without them this is reported evidence quality. Raw tool traces, private reasoning and archived manifests are not supplied to the normal semantic call.

Naming Chaos Mesh, fault injection, or another synthetic mechanism is neither
required nor rewarded. If an agent uses that terminology, the judge treats the
words themselves as neutral and independently grades whether the result names
the correct observable condition, target, scope, evidence, causal impact, and
remediation.

Requests, raw model output, anomalies, tool calls, reasoning, session traces,
learning records, and remediation-session exports are not read. The judge runs
at temperature zero with a strict per-criterion response object:

```json
{
  "root_cause_correctness": {"class": "MOSTLY_CORRECT", "reason": "concise evidence-specific reason"}
}
```

Allowed `class` values are the enums from `rubric.json`. Each reason is at most
500 characters. Running and result-less jobs, plus individual judge failures, remain visible as
`not_evaluable`. Failed jobs with final results receive the same rubric and
remediation-penalty assessment as succeeded jobs.

Alignment is derived in code from the first criterion of that kind
(root-cause correctness or remediation correctness). A job is `aligned` when
that criterion's score is at least 0.75, otherwise `not_aligned`. Alignment
does not use penalty results.

## Remediation penalties

Remediation-only. After rubric classification, if
`resources/penalties/<scenario-name>.json` exists and is non-empty, the judge
makes a second structured call. That penalty-only call receives the archived
manifests so it can detect evaluation tampering and target-specific harmful
actions. Each file is a JSON array:

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
and final result JSON. Penalty cache keys additionally include normalized
manifests and the penalty-file hash. Editing `rubric.json` therefore invalidates
old rubric checkpoints. `JUDGE_MAX_TOKENS` or `--judge-max-tokens` controls the
response allowance; the 8,192-token default accommodates local reasoning
models.

## Incident recovery replaces job-centered metric grading

See [the current methodology](../docs/methodology.md), [complete metric reference](../docs/metrics.md), and [portable evidence contract](../docs/evidence-contract.md).

Original Runner archives are graded directly: Locust CSV counter differences supply reliability and goodput; baseline-active services are assessed individually for latency and traffic. The result is an explicitly labelled service recovery proxy, independent of job completion and judge success. No new Runner outputs are required. Strict client-histogram recovery, verified actions and safety remain separate optional measurements.

Per-run `grade.json` retains archive outcomes and their evidence; `grade.json` retains schema 2 and records methodology `archive-recovery-v3`. Use `--operational-only` for offline calculations without model calls. The Grader owns `evaluation-policy.json`. See the methodology for missing data and percentile limitations.

## Outputs

For each run, the grader writes:

- `grades/runs/<run>/grade.json`: normalized grading inputs, each final job
  result, rubric classifications and scores, derived alignment, every metric
  family and series, and final grades;
- `grades/runs/<run>/report.md`: concise RCA, remediation, criterion, and
  family summaries;
- `grades/runs/<run>/judge-cache.json`: hash-keyed classification checkpoints.

New output directories contain only:

```text
runs/<run>/grade.json
runs/<run>/report.md
runs/<run>/judge-cache.json
logs/grader.log
csvs/summary.csv
csvs/rca_rubric_score.csv
csvs/remediation_rubric_score.csv
csvs/window_comparison.csv
csvs/scenario_table.csv
```

The three job CSVs preserve `status` and `is_failed`. Remediation totals include
`rubric_score` and `penalty_total`. The scenario CSV has per-run session summaries
and paired best/worst front-end metrics. Window CSVs disclose zero-imputation
counts. Empty input still writes all five CSV headers.

Aggregate Markdown, paper metrics, research-summary and incident files are no
longer generated. Existing historical outputs are preserved; choose a fresh
output directory to get the clean layout. Per-run JSON retains measurement and
scoring provenance. The analyzer accepts `csvs/` and legacy flat directories.

The per-run JSON has this stable top-level shape (nested manifests, results,
and available diagnostic summaries are retained):

```json
{
  "schema_version": 2,
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

### Sliding comparisons

`--comparison-window-minutes 5` configures baseline versus best/worst scheduled-chaos
window comparisons (default five minutes), including in `--operational-only` mode.
See the [component guide](../README.md#baseline-versus-bestworst-chaos-windows) for
metric definitions, missing-data handling, and `window_comparison.csv` fields.

## Paired scenario table

Each grading run writes `csvs/scenario_table.csv`. The original twelve columns retain scenario, score
maxima/means, baseline P95/5xx, paired best-window values/location, and exported
session counts. Three appended columns give worst-window P95, its paired 5xx
rate, and its UTC location. Three further columns count imputed 5xx samples in
the baseline, best, and worst intervals.

The default workload is `front-end`. Use `--table-workload NAME` for another
entry point and `--table-namespace NAME` if the name occurs in multiple namespaces.
No other workload is silently substituted.

Baseline means exclude the first **five minutes** of the recorded baseline by
default. Set `--baseline-ignore-minutes 0` for the full baseline or another
nonnegative duration. A recorded 30-minute baseline therefore uses minutes 5–30.
If exclusion leaves no interval, baseline values remain unknown. Missing baseline
measurements do not block valid chaos-window measurements.

`--comparison-window-minutes` controls window length (default five minutes).
Windows scan the entire recorded chaos interval, advancing by the scrape step,
independently of RCA/remediation timing. They must fit within a single chaos
interval before cleanup; idle gaps and cleanup are excluded. The recorded
boundaries are used rather than assuming every archive lasts exactly one hour.

- **Best:** lowest mean P95 among windows with mean 5xx <= 0.5 requests/s;
  override the ceiling with `--table-max-5xx-rate`.
- **Worst:** highest mean P95 among all covered windows, without a 5xx ceiling.
- Both selections break ties by earliest time. Each selected P95/5xx pair uses
  exactly the same window. If no window meets the best threshold, worst may
  still be available.

P95 is the time mean of archived rolling workload P95 estimates, not a pooled
client percentile. HTTP 5xx is requests/s, not a percentage. Each reported metric
needs two samples and 90% coverage in its own interval. Both metrics must meet
coverage for a paired chaos window; baseline validity is assessed independently.
As explicitly requested, missing 5xx samples from a successful result matrix
are imputed as zero at matching recorded traffic timestamps. Counts are disclosed
in both window CSVs and per-run JSON. Missing query files, traffic gaps and
explicit nonfinite samples remain unavailable. P95 is never zero-filled.

Score maxima and means include scored succeeded and failed jobs; remediation
uses final scores after penalties. Session counts include every exported job;
scored denominators can be obtained from the job CSVs. One row represents one archived
run, even when scenario names repeat. Per-run JSON records selection settings, trimmed
baseline boundaries, coverage, counts, and unknown reasons in `paired_window`.
Recovery scoring and independent per-workload comparisons are unchanged.
