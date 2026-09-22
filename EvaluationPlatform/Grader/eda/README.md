# Markdown metrics report

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

The report contains per-scenario maximum/average scores, chaos-only session
counts, time from chaos start to the first highest-scoring output, baseline and
best/worst P95 and 5xx values and differences, aggregate success counts, and
attempt/coverage/exclusion details. By default it selects the latest completed
attempt for each scenario, falling back to the latest attempt when none completed.

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
