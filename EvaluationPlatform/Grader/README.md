# Offline grader and visualizer

The Grader reads archived evaluation runs and produces three separate assessments:

1. **Semantic output quality:** RCA/remediation rubric scores and remediation penalties.
2. **Descriptive performance:** baseline versus selected best sliding chaos windows.
3. **Archive service recovery proxy:** sustained latency/reliability/throughput recovery
   under `archive-recovery-v3`, retained in per-run JSON.

Job success, semantic alignment and service recovery are different outcomes.
No cluster access, Runner rebuild, new telemetry, or extra experiments are needed.
Source archives are read-only; use a new output directory to preserve old reports.

## Run

From `EvaluationPlatform/Grader/` (or the root of a standalone Grader copy), install
`requirements.txt`. Configure the judge with `JUDGE_URL`, `JUDGE_MODEL` and
`JUDGE_TOKEN`, or CLI options. If using `.env`, export its settings into the
process; the CLI does not automatically load that file. Keep it untracked.

```bash
# Semantic judging plus archive measurements:
python -m grader --input results/sock-shop-1 --output output/grades/new-assessment

# Archive measurements only; no model calls:
python -m grader --input results/sock-shop-1 --output output/grades/new-offline-assessment --operational-only

# Configure both descriptive comparisons and the paired scenario table:
python -m grader --input results/sock-shop-1 --output output/grades/new-window-assessment \
  --comparison-window-minutes 5 --baseline-ignore-minutes 5 \
  --table-workload front-end --table-namespace sock-shop --table-max-5xx-rate 0.5

# Offline plots:
python -m visualizer --input results/sock-shop-1 --output output/visualizations/new-assessment
```

`./grade.sh` runs the visualizer for all three applications, then the grader,
then writes `output/report/report.md` through `reporting/report.py`. Select applications
with `--apps sock-shop teastore` or `--input results/online-boutique`. Grader
options follow `--`, for example:

```bash
./grade.sh --apps sock-shop --output-root /tmp/grader-check -- --operational-only
```

Use `--output-root` to preserve existing outputs during checks. See the
[pipeline and reporting guide](reporting/README.md) for configuration. Legacy
`--window-minutes` and `--threshold` are rejected; recovery policy overrides use
`--evaluation-policy resources/evaluation-policy.json` or another policy file.

## Current output layout

```text
output/
  report/
    report.md
    report-applications.png
  visualizations/<app>/
  grades/<app>/
    csvs/
      summary.csv
      rca_rubric_score.csv
      remediation_rubric_score.csv
      window_comparison.csv
      scenario_table.csv
    runs/<run>/
      grade.json
      report.md
      judge-cache.json
    logs/grader.log
```

Start with `csvs/scenario_table.csv` for one row per archived run: semantic score
maxima/means, exported session counts, baseline P95/5xx, paired best windows
and imputation counts. Use `window_comparison.csv` for the client mean estimate
and independent per-workload comparisons. Detailed recovery outcomes and reasons
are in `runs/<run>/grade.json` → `research.operational`.

Normal grading no longer emits aggregate `incidents.*`, `paper_metrics.csv`,
`research_summary.*`, or `scenario_table.md/json`. Historical files are preserved.
Job CSVs do not provide a complete run inventory when sessions are empty.

## Baseline versus best chaos windows

There are **two descriptive comparisons**; neither changes recovery scoring:

| Report | Baseline | Best selection |
| --- | --- | --- |
| `window_comparison.csv` / `window_comparison` | Full recorded baseline | Lowest covered value independently per metric/workload |
| `scenario_table.csv` / `paired_window` | Baseline minus first 5 minutes by default | Lowest P95 with 5xx ≤0.5 requests/s. P95 and 5xx share the selected window |

Windows default to five minutes (`--comparison-window-minutes`, positive fractional
values supported). They advance by the recorded scrape step inside individual
recorded chaos intervals before cleanup, without bridging idle gaps. Earliest
windows break ties. At least 90% coverage is required. Set
`--baseline-ignore-minutes 0` to use the full baseline in the paired table.
The recovery proxy separately uses the **last five baseline minutes** by default.

- **Client mean:** estimated from differences in cumulative Locust count × mean;
  reported in seconds. CSV rounding and missing response timings limit accuracy.
- **Service P95:** time average of archived rolling workload P95 samples, in seconds;
  not a pooled client percentile.
- **HTTP 5xx:** requests/second, not a percentage or client failure ratio.
- **Missing 5xx:** descriptive windows explicitly impute absent samples as zero at
  matching traffic timestamps in successful query matrices. Counts disclose this
  assumption. Failed queries, traffic gaps and explicit invalid values remain unknown.

See [metrics](docs/metrics.md) for units, formulas, coverage and all current outputs.

## Archived inputs and status interpretation

Runs are discovered by `metadata.json`. Semantic grading requires archived
`inputs/scenario.json`, referenced `inputs/chaos/*.yaml`, and matching ground truth.
Metrics come from local `metrics/*.json` and `loadgenerator/*.csv` files. The grader
never follows old pod paths or endpoint addresses stored in metadata.

Semantic job inputs are `sessions/rca_session.json` and
`sessions/remediation_run.json`. **Succeeded and failed jobs with nonempty final
`result` objects** are eligible. Running/result-less jobs and judge failures remain
explicitly non-evaluable. Status and `is_failed` are preserved in the job CSVs.
Raw output, private reasoning and tool traces do not replace final results.

Current RemediatorAgent `succeeded` means final output was produced, not verified
execution/recovery. Top-level grading status `graded` means input processing
completed; a setup-failed run can still have that status with no job scores.
Empty session arrays do not distinguish no anomalies from interrupted startup,
no-agent execution or export problems. Inspect `metadata.json`, `run-status.json`,
`runner.log`, hook logs and `sessions/anomaly.json` when diagnosing them.

Other bundled session exports support investigation and timeline visualization.
Original archives are sufficient; optional portable evidence is described in the
[input contract](docs/evidence-contract.md).

## Resources and guides

`resources/` owns `rubric.json`, `evaluation-policy.json`, `scenario-policy.md`,
`ground_truth/`, and `penalties/`. Defaults resolve relative to source code;
explicit CLI overrides are supported. Ground truth is never generated during grading.

- [Grader CLI, scoring and cache guide](grader/README.md)
- [Metric reference](docs/metrics.md)
- [Recovery and reporting methodology](docs/methodology.md)
- [Archive input contract](docs/evidence-contract.md)
- [Validation guide](docs/validation.md)
- [Visualizer](visualizer/README.md)
- [Markdown report CLI](reporting/README.md) — run `python -m reporting.report` to generate `output/report/report.md`.
- [Offline synthetic reporting demo](reporting/README.md#offline-demonstration) — renders a report and application chart from two small prepared examples without a judge or cluster. The example is not research data.

## Scenario metrics report

Run `python -m reporting.report` to read existing `output/grades/<app>` and
`results/<app>` and generate `output/report/report.md` offline. The Python
report calculates scenario scores, chaos-only sessions and timing, baseline and
best-window differences, and application comparisons. Missing evidence stays
unknown. Completed-run summaries disclose their denominators and keep an audit
of excluded attempts. See the [reporting guide](reporting/README.md) for options.

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
The Python reporting script applies the same filter to historical grades and exposes excluded
session counts. Historical grade files and judge caches are not rewritten by
report generation. Whole-run cumulative client mean/P95 summaries are omitted
from chaos-only metrics.
