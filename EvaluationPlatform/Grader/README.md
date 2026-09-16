# Offline grader and visualizer

Install `requirements.txt`. Copy `.env.example` to ignored `.env`, fill judge settings, and export them with `set -a; . ./.env; set +a` before grading. `python -m grader --input results --output grades/new-assessment` invokes the grader. The local `grade.sh` does not forward extra arguments. Configure judge access through the CLI described in [grader/README.md](grader/README.md). `PYTHONPATH=. python -m visualizer --input ../Runner/results --output visualizations` renders archived metrics without a model or cluster.

The default method is **archive-recovery-v3**. It grades the original Runner archives using Locust CSV counters, per-service Prometheus metrics, recorded chaos timing and session outputs. **No Runner rebuild, extra scenario, paired run or longer experiment is required.** Existing reports are preserved by selecting a new output directory.

- [Metric reference](docs/metrics.md): the 13 telemetry families, rubric criteria, penalties and archive-derived measurements.
- [Research methodology](docs/methodology.md): exact calculations, proxy limitations, denominators and judge calibration.
- [Existing archive input contract](docs/evidence-contract.md).
- [Offline validation](docs/validation.md).

```bash
python -m grader --input results/sock-shop-1 --output grades/sock-shop-1-v3
# No model calls; semantic grading explicitly skipped:
python -m grader --input results/sock-shop-1 --output grades/sock-shop-1-offline --operational-only
```

`runs/<run>/grade.json` retains each scenario's **service recovery proxy**, actual client failure ratio, successful throughput and measured failed requests. Semantic scores remain separate. The proxy cannot prove active-fault recovery, safe execution or causal benefit. Those claims remain unknown without supporting evidence and do not block the archive assessment.

The evaluation policy is local to the Grader: `resources/evaluation-policy.json`. `--evaluation-policy PATH` records an offline override. Legacy `--threshold`/`--window-minutes` scoring options are rejected with a migration message. No additional research suites are installed in Runner.

## Directory layout

```text
grader/                   Python grading code
visualizer/               Plotting code
resources/
  rubric.json             Scoring criteria and weights
  evaluation-policy.json  Recovery thresholds and methodology
  scenario-policy.md      Shared scenario grading policy
  ground_truth/           Scenario reference diagnoses and remediations
  penalties/              Scenario-specific penalty definitions
docs/                     Methodology and metric documentation
tests/                    Offline tests
grades/                   Generated grading reports
visualizations/           Generated charts
```

Default resource paths resolve relative to the installed source tree, independent
of the working directory. CLI resource overrides remain supported. Scripts using
explicit old `grader/rubric.json`, `grader/evaluation-policy.json`,
`grader/ground_truth`, or `grader/penalties` paths should use `resources/` instead.

## Exporter contract

Every run folder supplies `metadata.json` (existing version 2), `inputs/scenario.json` with name/application/placement/steps, and `inputs/chaos/<reference>.yaml` for every referenced chaos resource. Placement definitions and their fingerprints remain necessary for comparable runs. Metrics retain the existing Prometheus JSON query-response layout documented by the runner collectors.

Online Boutique's standard scenarios use `online-boutique-` names. Matching
ground-truth and penalty files are provided; the historical `real-` files remain
available so archived runs can still be graded without changing their inputs.

Semantic grading reads these JSON arrays:

- `sessions/rca_session.json`: objects with `id`, `workflow_id`, `status`, lifecycle timestamps including `created_at` and `completed_at`, and a non-empty `result` for successful jobs. The final result describes the diagnosis and evidence.
- `sessions/remediation_run.json`: the same lifecycle fields, plus the final remediation/verification `result`. Job timestamps support queue/execution diagnostics; recovery uses observed fault and client timestamps.

Other fields are preserved; audits are not used as substitutes for final results. Empty arrays are valid for a no-agent run. Succeeded and failed jobs with non-empty final results receive semantic scores;
running or result-less jobs and missing inputs remain explicitly unevaluable.
Job CSVs preserve `status` and include an `is_failed` flag. Ground truth is selected by the archived scenario name. Researchers provide their own Markdown ground truth, rubric configuration and penalties where necessary.

Bundled exports additionally include `anomaly.json`, `remediation_session.json` (tool calls and artifacts), `learning_session.json` (lessons), and `workflow.json`. These support investigation and timeline visualization. A custom solution need not implement the bundled database schema or internal job APIs: its post-run script maps its final outputs into the two grading arrays.

`Runner/hooks/postrun/example-export/run.sh` produces synthetic files demonstrating this interface. It is not selected by bundled scenarios and must not be used as evidence from a real solution. See the detailed [grader](grader/README.md) and [visualizer](visualizer/README.md) guides for output schemas and limitations.

## Analysis and historical archives

Run `python analyzer.py` from this directory to summarize `../Runner/results` with `grades/`. Override the positional grade directory, `--root`, `--results`, and `--output` as needed (`python analyzer.py --help`). Existing `grades/` and `visualizations/` archives were moved here unchanged. Ground truth and penalties for retired smoke scenarios remain available for historical grading.

## Baseline versus best/worst chaos windows

Grading also writes `window_comparison.csv`, a `window_comparison` object in each
run's `grade.json`, and a comparison table in each run's `report.md`.

```bash
python -m grader --input results/my-campaign --output grades/my-comparison --operational-only --comparison-window-minutes 5
```

The default window is five minutes; positive fractional minutes are supported.
The reference is the **full recorded baseline** in the same run. Full windows
advance by the archived Prometheus scrape step (normally 15 seconds) within each
recorded chaos interval, ending before cleanup. Windows never bridge idle steps
or extend into recovery. Missing chaos-end timestamps exclude that step.

Best and worst are selected **independently for each metric and workload**, with
lower values preferred and earliest timestamps breaking ties. Reports show the
baseline, selected values, absolute/relative changes, UTC start/end, and coverage.
Zero baselines have an absolute change but no relative percentage. At least 90%
coverage is required in the baseline and each candidate; missing data is unknown.

- Client mean response time is an **estimate** from cumulative Locust request
  counts and cumulative mean response times: `(N2*M2 - N1*M1)/(N2-N1)`.
  It assumes all counted requests have a response time; CSV rounding can affect
  the estimate. Counter resets and insufficient coverage invalidate windows.
- Service P95 is the **time average of archived rolling P95 samples**, separately
  for each namespace/workload. It is not the pooled P95 of requests in five minutes.
- HTTP 5xx rate is the time average of archived **requests/second**, per workload;
  it is not the client failure ratio. Reduced traffic can lower this rate.

Prometheus samples represent at most one scrape interval; gaps are not filled.
Existing rolling query windows can include observations preceding a boundary.
These descriptive comparisons do not alter recovery policy or semantic scores.

## Output layout for notebooks

New grading outputs contain `runs/`, `logs/grader.log`, and `csvs/` with exactly:
`summary.csv`, `rca_rubric_score.csv`, `remediation_rubric_score.csv`,
`window_comparison.csv`, and `scenario_table.csv`. Aggregate incident files,
paper metrics and aggregate Markdown/JSON summaries are no longer generated.
Historical outputs are preserved; use a fresh `--output` directory.

The scenario table contains score maxima/means, session counts, baseline P95/5xx,
and paired best/worst front-end chaos windows. Baseline excludes its first five
minutes by default (`--baseline-ignore-minutes`). Best minimizes P95 subject to
5xx <= 0.5 requests/s; worst maximizes P95 without that ceiling. Windows scan the
entire recorded chaos interval independently of remediation timing.

Missing 5xx samples in successful query matrices are imputed as zero where
matching traffic samples exist, as requested. Imputed counts are disclosed in
CSV columns; latency, failed queries and traffic gaps are not zero-filled.
See [configuration and definitions](grader/README.md#paired-scenario-table).
