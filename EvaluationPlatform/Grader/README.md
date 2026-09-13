# Offline grader and visualizer

Install `requirements.txt`. Copy `.env.example` to ignored `.env`, fill judge settings, and export them with `set -a; . ./.env; set +a` before grading. `./grade.sh --input ../Runner/results --output grades` invokes the existing grader. Configure judge access through the CLI described in [grader/README.md](grader/README.md). `PYTHONPATH=. python -m visualizer --input ../Runner/results --output visualizations` renders archived metrics without a model or cluster.

Scoring, rubric classifications, penalties, metric windows, caches and report formats are unchanged. Both historical runs and runs from the new Runner are supported.

## Exporter contract

Every run folder supplies `metadata.json` (existing version 2), `inputs/scenario.json` with name/application/placement/steps, and `inputs/chaos/<reference>.yaml` for every referenced chaos resource. Placement definitions and their fingerprints remain necessary for comparable runs. Metrics retain the existing Prometheus JSON query-response layout documented by the runner collectors.

Semantic grading reads these JSON arrays:

- `sessions/rca_session.json`: objects with `id`, `workflow_id`, `status`, lifecycle timestamps including `created_at` and `completed_at`, and a non-empty `result` for successful jobs. The final result describes the diagnosis and evidence.
- `sessions/remediation_run.json`: the same lifecycle fields, plus the final remediation/verification `result`. Metric windows are centered on `completed_at`.

Other fields are preserved; audits are not used as substitutes for final results. Empty arrays are valid for a no-agent run. Unsuccessful jobs and missing inputs remain explicitly unevaluable. Ground truth is selected by the archived scenario name. Researchers provide their own Markdown ground truth, rubric configuration and penalties where necessary.

Bundled exports additionally include `anomaly.json`, `remediation_session.json` (tool calls and artifacts), `learning_session.json` (lessons), and `workflow.json`. These support investigation and timeline visualization. A custom solution need not implement the bundled database schema or internal job APIs: its post-run script maps its final outputs into the two grading arrays.

`Runner/hooks/postrun/example-export/run.sh` produces synthetic files demonstrating this interface. It is not selected by bundled scenarios and must not be used as evidence from a real solution. See the detailed [grader](grader/README.md) and [visualizer](visualizer/README.md) guides for output schemas and limitations.

## Analysis and historical archives

Run `python analyzer.py` from this directory to summarize `../Runner/results` with `grades/`. Override the positional grade directory, `--root`, `--results`, and `--output` as needed (`python analyzer.py --help`). Existing `grades/` and `visualizations/` archives were moved here unchanged. Ground truth and penalties for retired smoke scenarios remain available for historical grading.
