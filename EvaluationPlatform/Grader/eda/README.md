# Markdown metrics report

## Interactive notebook

Open `report.ipynb` from the Grader checkout and run all cells. One run reads
`online-boutique`, `sock-shop`, and `teastore` from their respective `grades/`
and `results/` folders. Each application uses its own entry workload and
namespace. Scenario selection and aggregate denominators are calculated within
each application before results are combined. Application comparison tables and
raw measurement CSVs identify the application; pooled and fault-family totals
combine applications explicitly. If an application has neither grades nor
archives, the notebook stops with a named missing-input error so a partial
report is not mistaken for a complete one.

Edit the shared thresholds and repeat policy in the first code cell. Set
`SHOW_DETAILS = True` for the attempt audit and `EXPORT = True` to create a
timestamped `eda/exports/` directory with CSVs, configuration for all three
applications, and the compact score Markdown table. It reads existing data
offline and does not call the judge.

## Markdown script

Run from any working directory:

```bash
python /path/to/Grader/eda/report.py
```

Or, from this directory:

```bash
python report.py
```

The script writes **`eda/report.md`**, replacing the previous generated report.
It reads matching application folders under `results/` and `grades/` for
`sock-shop`, `online-boutique`, and `teastore`. Absent applications are noted and
skipped. Archives are discovered recursively, including `previous-local`.
Duplicate run names in different archive directories produce an error instead
of silently selecting one. No judge calls occur and input files are unchanged.
Ungraded archives still contribute performance metrics and session counts;
semantic scores remain unknown until grades exist.
Input locations in the public Markdown and notebook configuration display use
Grader-relative paths. Inputs outside the checkout appear as an external input
label so a generated report does not disclose a workstation directory tree.

## Offline demonstration

From `EvaluationPlatform/Grader/`, run this on a fresh checkout after installing
the Grader requirements:

```bash
python eda/report.py \
  --results-dir examples/report-demo/results \
  --grades-dir examples/report-demo/grades \
  --apps sock-shop online-boutique \
  --output /tmp/incidentbench-demo-report.md
```

Open `/tmp/incidentbench-demo-report.md` and the companion
`/tmp/incidentbench-demo-report-applications.png`. The fixture is deliberately
**synthetic**: two made-up completed runs demonstrate a score above and below
the 0.8 threshold, timing, denominators, and application comparison. It is not
an experiment result or evidence about IncidentBench performance. There are no
telemetry series in the fixture, so P95, 5xx, and window tolerance remain
`Unknown` with their evaluable denominator at zero. No cluster, judge, or network
connection is used. Actual raw archives and grades are intentionally not bundled;
the checked-in `report.md` is a curated example from the local research run.

The report contains per-scenario maximum/average scores, chaos-only session
counts, time from chaos start to the first highest-scoring output, baseline and
best/worst P95 and 5xx values and differences, aggregate success counts, and
attempt/coverage/exclusion details. By default it selects the latest completed
attempt for each scenario, falling back to the latest attempt when none completed.
The completed-run analysis reproduces the numeric summary families in
`../analysis.md` from the current archives and grades: cohort, semantic success,
score means, session and timing distributions, window tolerance and P95 changes,
semantic/performance cross-tabulations, and fault-family comparisons. Pooled rows
show their denominators. A PNG beside the Markdown report compares application
scenario success and window tolerance with counts on every bar. The earlier
per-scenario and all-selected-run tables remain an audit; incomplete selected
runs are excluded from the completed-run analysis. The notebook uses the same
summary calculations and displays at most one table in each cell. Completion
requires completion in metadata or run-status, a zero or absent execution return
code, and no failed/interrupted status in either source. Session totals sum only
runs with known in-chaos counts and display how many runs have known counts.

```bash
python report.py --window-minutes 5 --score-threshold 0.8 \
  --p95-change-limit 0.20 --max-5xx-rps 0.5 \
  --apps sock-shop online-boutique --output my-report.md
```

Other options: `--results-dir`, `--grades-dir`, `--baseline-ignore-minutes`, and
`--repeat-policy all_runs`. Relative CLI paths resolve from the current working
directory; default paths resolve from the script location. Entry workloads are
`front-end`, `frontend`, and `teastore-webui` respectively, in application-named
namespaces. All thresholds and measurement caveats appear in the Markdown file.
