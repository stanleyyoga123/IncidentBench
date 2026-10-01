# Python experiment reporting

Run the full pipeline from the Grader root:

```bash
./grade.sh
./grade.sh --apps sock-shop teastore
./grade.sh --input results/online-boutique
./grade.sh --apps sock-shop --output-root /tmp/grader-check -- --operational-only
```

The default applications are `online-boutique`, `sock-shop`, and `teastore`.
All selected applications are visualized first, graded second, and included in
one Markdown report last. Missing input directories or failing commands stop
the pipeline. `--input` selects one application directory with one of those
names; it cannot be combined with `--apps`. Relative input and output-root paths
resolve from the caller's working directory.

All generated files use one default root:

```text
output/
  grades/<app>/
  visualizations/<app>/
  report/report.md
  report/report-applications.png
```

Folders are created automatically. `--output-root PATH` places `grades`,
`visualizations`, and `report` under PATH and preserves the default outputs.

Grader options follow `--`. Use `--operational-only` for zero model calls.
Ordinary grading uses the configured judge. Input/output and workload/namespace
are owned by the pipeline; forwarded grader option names must be written in
full. Overrides of `--comparison-window-minutes`, `--baseline-ignore-minutes`,
and `--table-max-5xx-rate` also update the report settings. Forwarded resource
paths resolve from the Grader root.

`PYTHON` overrides the interpreter executable; otherwise `.venv/bin/python`,
`python`, then `python3` are tried. Judge configuration supports `JUDGE_URL`,
`JUDGE_MODEL`, `JUDGE_TOKEN`, `JUDGE_TIMEOUT_SECONDS`, `JUDGE_MAX_TOKENS`, and
`GRADER_CONCURRENCY`, or forwarded grader options. Existing launcher defaults
retain its configured local endpoint, `Qwen/Qwen3.6-35B-A3B`, 600-second timeout,
8192-token allowance, and five workers.

To generate only the report from existing archives and grades:

```bash
python -m reporting.report
python -m reporting.report --apps sock-shop --output /tmp/my-report.md
```

This reads `results/<app>` and `output/grades/<app>` and writes
`output/report/report.md` without model calls. The companion chart is generated
when data is available. Default paths resolve from the Grader root; explicit
relative paths resolve from the caller's working directory. From another working
directory, run `python /path/to/Grader/reporting/report.py`.

The report covers scenario maximum/mean scores, in-chaos session counts and
timing, baseline and best-window performance, application comparisons,
completed-run summaries, fault-family outcomes, and coverage/exclusion audits.
Unknown evidence stays unknown. Missing applications are labelled and skipped.
The latest completed attempt is selected per scenario by default, falling back
to the latest attempt when none completed. `--repeat-policy all_runs` includes
all attempts. Workloads are `frontend`, `front-end`, and `teastore-webui` in
application-named namespaces.

Options include `--results-dir`, `--grades-dir`, `--window-minutes`,
`--score-threshold`, `--p95-change-limit` (fraction), `--max-5xx-rps`, and
`--baseline-ignore-minutes`. Run `python -m reporting.report --help`.

## Offline demonstration

```bash
python -m reporting.report \
  --results-dir examples/report-demo/results \
  --grades-dir examples/report-demo/grades \
  --apps sock-shop online-boutique --output /tmp/demo-report.md
```

These inputs are synthetic demonstrations, not experiment results. Their
telemetry is absent, so performance remains unknown with explicit denominators.
No cluster, judge, or network connection is used.
