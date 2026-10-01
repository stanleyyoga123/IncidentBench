# Evaluation timeline visualizer

This standalone package renders Prometheus metrics and the archived lifecycle
of each evaluation run. It does not inspect agent reasoning and does not
contact the cluster, model, or other services.

From `EvaluationPlatform/Grader/` (or a standalone Grader root), run:

```bash
python -m visualizer --input results/sock-shop-1 --output output/visualizations/new-assessment
```

The default input is `results/result-3` and the default output is
`output/visualizations` under the Grader root. Both are configurable:

```bash
PYTHONPATH=. python -m visualizer \
  --input results/my-result-set \
  --output output/visualizations/my-result-set \
  --format both \
  --view all \
  --dpi 180
```

`--input` can name either one run directory or a parent containing multiple run
directories. For each run, the visualizer reads `metadata.json` and the
optional `sessions/anomaly.json`, `rca_session.json`, `remediation_run.json`,
and `remediation_session.json` exports, plus every Prometheus query-range JSON
under `metrics/` except the aggregate `metrics.json` file.

The default `--view all` creates all three requested groups. A single group can
be selected with `--view metrics-only`, `--view metrics-with-timeline`, or
`--view timeline-only`.

- `metrics-only`: one multi-series line plot per metric family.
- `metrics-with-timeline`: one figure per metric family with the metric above
  and the complete lifecycle timeline below on the same elapsed-time x-axis.
- `timeline-only`: the lifecycle timeline without metric lines.

The plot uses `metadata.started_at` as elapsed minute zero. It contains lanes
for the active chaos interval, anomaly detections, RCA start and finish,
remediation start and finish, and every `remediator.run_ansible` call. Ansible
check-mode and live-mode calls are shown separately. If the run start is
missing, the earliest valid event becomes the origin and the report records a
warning.

Output layout:

```text
output/visualizations/
  report.md
  runs/<run>/
    metrics-only/
      <metric>.png
      <metric>.svg
    metrics-with-timeline/
      <metric>.png
      <metric>.svg
    timeline-only/
      timeline.png
      timeline.svg
      events.csv
```

`events.csv` preserves the ISO timestamp, elapsed minutes, event/interval kind,
job and workflow identifiers, label, and recorded status used to construct the
figure. Each line is labelled by deployment, destination workload, node, or the
best remaining Prometheus identity label. Missing optional session files
result in empty lanes rather than a failure. Invalid metadata or a run with no
timeline events is reported as a failure, while other runs continue rendering.

New archives additionally plot client P95 histogram estimates, failure ratio and successful throughput. These are distinct from per-service mesh metrics. Incident outcomes and methodology hashes are documented in the [research guide](../docs/methodology.md).

Original Runner CSV histories also produce client failure-ratio and successful-throughput charts from counter differences. Cumulative client P95 is not plotted as interval latency. No Runner instrumentation update is required.
