# Grader input contract: existing Runner archives

The supported default input is the previous Runner output, as in
`EvaluationPlatform/Runner/results/sock-shop-1`. No new evidence directory or
Runner change is required.

| File | Fields used | Purpose |
| --- | --- | --- |
| `metadata.json` | `metrics.start/end/step_seconds`, `baseline_seconds`, `baseline_health`, `phases`, `chaos_steps`, `status`, `application` | Baseline, scheduled fault and observation boundaries; validity |
| `loadgenerator/*_stats_history.csv` | `Name=Aggregated`, `Timestamp`, `Total Request Count`, `Total Failure Count` | Client interval counters and coverage |
| `loadgenerator/*_stats.csv` | Aggregate counts, `95%`, `Average Response Time` | Whole-run client diagnostics |
| `metrics/*.json` | `data.result[].metric` and `values` | All original telemetry families; individual-service proxy checks |
| `inputs/scenario.json`, archived chaos YAML | Existing scenario names and faults | Semantic ground truth matching and penalties |
| `sessions/rca_session.json`, `remediation_run.json` | IDs, status, result and actual lifecycle timestamps | Semantic outputs, attempts and available timings |
| `sessions/remediation_session.json` | Existing tool-call arrays | Available audit counts, not proof of execution |
| `run-status.json` | status | Infrastructure failure/interruption |

Paths embedded in old metadata can reference the original pod. The Grader reads
local archive-relative files and never contacts those endpoints. It never changes
archives, runs hooks, creates scenarios, or controls the cluster. Counts and
recovery bins reference CSV lines and metric labels/times in the output.
Missing evidence remains null/unevaluable; it is never reconstructed from prose.

## Optional richer evidence

For compatibility with independently supplied evidence, the Grader can also read
`evidence/client-intervals.jsonl`, `events.jsonl`, `actions.jsonl`, `observations.jsonl`,
`safety.json`, `experiment.json`, and `model-usage.json`. These are **optional**;
there is no bundled Runner producer after the rollback. They do not gate grading
of original archives. Portable client-histogram outcomes have a separate
`measurement_basis` and cannot be pooled with archive recovery proxies.

Portable events/actions/observations require schema version 1, matching run and
incident IDs, UTC timestamp, event type, source and existing archive-contained
`evidence_refs`. Independent safety assessments use event type `safety_assessment`,
`coverage_complete: true`, and a `critical_violations` list. A nonempty confirmed
list is a hard safety failure; an empty list with complete coverage can support
verified safety. A source label does not itself prove assessor independence.
Applied action evidence requires `action_applied` with `data.verified: true` and
references. Tool-call success alone does not meet this condition.

Portable client intervals require start/end, observed seconds, nonnegative attempted
and failed counts, and sorted noncumulative `[upper_bound_seconds,count]` histogram
bins accounting for every attempt. No overlap or nonfinite values are accepted.
Do not synthesize these records from old CSV percentiles. Model cost requires
actual usage and dated prices. Detector recall/delay requires reviewed alert
matches and coverage; false-alert rates need agents-enabled healthy controls.
Absent optional evidence remains unknown without blocking ordinary archive grading.

Never include credentials, request bodies or private reasoning traces in optional
evidence bundles. Existing session results remain the semantic input contract.

## Semantic job eligibility

Succeeded and failed jobs with non-empty final `result` objects are scored.
Running and result-less jobs retain non-evaluable dispositions. The original
`status` is preserved; job CSVs add `is_failed` (`True` for `failed`, otherwise
`False`). A semantic score does not change execution or recovery outcomes.

## Output layout and descriptive 5xx assumption

New outputs use `runs/`, `logs/grader.log`, and five CSV files in `csvs/`.
Aggregate incidents, paper metrics and research summaries are no longer emitted.
Source archives remain immutable. By explicit user request, missing 5xx samples
in successful query matrices are imputed as zero for descriptive windows only,
at matching traffic timestamps. CSV counts and per-run JSON disclose this
assumption; raw recovery evidence and semantic score eligibility are unchanged.
