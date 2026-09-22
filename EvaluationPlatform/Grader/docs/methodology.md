# Offline archive grading methodology

The default method is **archive-recovery-v3**, using the original Runner output.
No Runner rebuild, new telemetry collector, additional scenario, paired run, or
longer experiment is required. The grader policy lives in
`resources/evaluation-policy.json`; `--evaluation-policy` selects a different offline
policy. Each report records its complete policy and SHA-256. Preserve old reports
by selecting a new output directory. Output schema remains 2, with explicit
measurement-basis and methodology fields.

## Measurement and incident boundaries

One run is one reporting unit, including all failed jobs and repeated attempts.
Semantic RCA/remediation grades use the existing session arrays and archived
scenario/ground truth. Succeeded and failed jobs with non-empty final result
objects are semantically eligible; running and result-less jobs remain
non-evaluable. Failed-job scores describe output quality, not execution success.
The job CSVs retain `status` and add `is_failed` (`True` for `failed`, otherwise
`False`). Run configuration records
`semantic_eligibility=succeeded-or-failed-with-final-result-v1`; unchanged judge
payloads retain their content-addressed checkpoints. Scenario-table score means include eligible failed-job scores; use the job CSVs
for scored denominators and per-run JSON for operational outcomes. Operational measurements are computed independently of
job success, completion time and judge availability. `--operational-only` skips
the judge entirely and still produces operational reports and job dispositions.

Read `metadata.metrics.start` as the recorded load/baseline start, and add
`metadata.baseline_seconds` to locate baseline completion. Use the last five
minutes before that boundary. Require a completed baseline phase and reject an
explicit failed `baseline_health` check or client failure ratio above 1%.
If no application health check was exported, disclose that limitation; do not
invent a passed check. Each 30-second baseline bin requires 90% CSV coverage
and at least 100 requests.

The observation window starts at the first non-idle chaos step's
`active_started_at` and ends at the earlier of recorded cleanup, the step duration cap, or the telemetry end. Idle gaps and post-chaos observation are excluded. The start records that
Runner applied the schedules; it is **not observed physical fault onset**.
Missing recorded boundaries are unevaluable, never replaced with job timestamps
or configured durations. Failed/interrupted infrastructure runs fail validity checks when reached.
Earlier missing-boundary or missing-counter checks can instead return
`not_evaluable`; always retain the source run status alongside the reason.

## Exact request counts and latency limitations

Use only `Name=Aggregated` rows from the one `*_stats_history.csv`. For any
window, take the first and last actual samples inside its boundaries:

- attempted = last Total Request Count − first Total Request Count;
- failed = last Total Failure Count − first Total Failure Count;
- failed-request ratio = failed / attempted;
- successful throughput = (attempted − failed) / measured elapsed seconds.

Counter resets or inconsistent counts make the window unknown. No interpolation
or invented requests are used. CSV gaps longer than five seconds contribute no
coverage. Counts across gaps can still be reported over their measured endpoints,
with the coverage fraction; they cannot establish a recovery streak. Incident
counts use the whole incident counter window, independently of the narrower
recovery bins, and disclose their exact endpoints and CSV line references.

The original Locust invocation lacks `--csv-full-history`. Its history percentile
columns are cumulative, according to the [Locust CSV writer source](https://docs.locust.io/en/2.41.1/_modules/locust/stats.html).
They cannot be subtracted or averaged into interval P95. The final aggregate
`*_stats.csv` P95 is a whole-run diagnostic, including baseline. Exact interval
client P95 and slow-request counts remain unavailable for these archives.

## Descriptive service recovery proxy

Since interval client histograms are unavailable, report an explicitly named
**archive service recovery proxy**, combining client counts with per-service
Prometheus P95 and traffic. This is a descriptive operational assessment, not a
verified safe-recovery grade or proof of agent effectiveness.

The service cohort contains every namespace/workload with positive baseline
`traffic_rps`. For each service separately, calculate the time median of baseline
`response_time_p95_seconds` samples and the time median of baseline traffic.
The median here summarizes repeated observations of one service; it is never
labelled application-wide P95 or pooled across healthy and harmed services.

Evaluate complete 30-second bins aligned to the archived Prometheus start.
Exclude partial incident edges. Each service needs at least two finite samples
per bin; the archived scrape step must be at most 15 seconds. Coverage credits
at most one scrape interval per sample, clipped at the bin boundary. Missing or
nonfinite latency/traffic breaks that bin. Baseline and total incident coverage
must each reach 90%.

A healthy bin requires all of the following:

1. Client counter coverage ≥90%, at least 100 requests, failure ratio ≤ baseline
   plus 0.001, and successful throughput ≥90% of baseline.
2. Every baseline-active service's maximum sampled P95 in the bin ≤120% of its
   own baseline P95 time median.
3. Every baseline-active service's minimum sampled traffic ≥90% of its own
   baseline traffic time median. This prevents a disappearing service or traffic
   shift from masquerading as improvement.

Require 120 consecutive seconds of healthy bins **after an observed degraded
qualifying bin**. Missing bins break the streak. No observed degradation yields
`no_observed_degradation`, rather than a fabricated zero-second recovery.
No qualifying streak by the recorded deadline yields `proxy_unresolved` and
right-censoring. Otherwise report `proxy_recovered` and
`proxy_recovery_seconds = streak start − recorded schedule start`.
The strict `recovery_seconds`, `recovered` and `active_fault_recovery` fields stay
unknown for this input format. This prevents proxy results from being mistaken
for the former histogram method.

`recovery_schedule_phase` says `during_scheduled_chaos` only if the entire streak
fits between a recorded step's schedule start and cleanup start. Otherwise it
says `after_schedule_cleanup` (or `unknown` for a boundary-crossing streak).
Neither label proves injection remained active: recurring faults can have idle
periods, and fault removal or HPA can explain improvement. Job completion does
not move the recovery timestamp. The thresholds are configurable research
choices; evaluate sensitivity without changing the original runs.

The proxy is deliberately conservative. Rate-window smoothing, request-mix
changes, low-rate asynchronous services and transient latency spikes can prevent
qualification. Publish per-service checks, coverage and absolute client metrics
alongside the outcome. Lower CPU/memory utilization is not itself recovery.

## Denominators, safety and uncertainty

`csvs/scenario_table.csv` contains one row per run; operational outcomes are
retained in each run's `grade.json` under `research.operational`. When aggregating
those outcomes yourself, report
proxy-recovered, proxy-unresolved, no-observed-degradation, insufficient-evidence
and invalid counts separately. Among assessable degraded incidents report
S/(S+F). Also report conservative missing-outcome bounds S/(S+F+U) through
(S+U)/(S+F+U), where U is insufficient evidence. These are identification bounds,
not statistical confidence intervals. Explicit no-degradation and invalid runs
are excluded from that recovery denominator and remain visible.

Safety, verified execution and semantic quality remain separate. A successful
job or tool return is not independent proof of applied changes or safety.
Unknown safety does not suppress the descriptive proxy. Confirmed critical
violations prohibit safe recovery even if the service improves. Optional
independent assessment files are described in the [input contract](evidence-contract.md).
The standard archive is sufficient to grade a scenario without supplying them.

No matched control is required. Without independently comparable agents-on/off
runs, paired treatment effect is unavailable and causal attribution is unsupported.
The extra CPU pilot/healthy suites and Runner instrumentation have been removed.
Existing user scenario suites are unchanged. Optional pair/bootstrap code is for
independently supplied matched evidence, not an instruction to execute more runs.
Do not treat jobs, requests or scrape samples as independent experimental repeats.

## Judge calibration and rubric sensitivity

Record the judge model revision, prompt version/hash and rubric hash. Independently
label a stratified sample of at least 60 available outputs using two human
reviewers, covering applications, fault families and contrasting outcomes. Blind
reviewers to automatic grades; adjudicate disagreements after independent labels.
If fewer outputs exist, use all and report incomplete calibration. The supplied
`python -m grader.calibration` computes per-criterion agreement, confusion tables
and quadratic weighted kappa from labels; it does not generate human judgements.
Report undefined kappa where there is no expected disagreement.

Publish criterion-level scores as well as weighted summaries. Compare equal
weights and correctness-emphasized weights; report ranking sensitivity.
Evidence-grounding without independently referenced observations is labelled
reported evidence quality. Fluent explanations and high semantic safety scores
cannot establish actual service recovery or absence of harm.

## Primary references

- [Locust statistics implementation](https://docs.locust.io/en/2.41.1/_modules/locust/stats.html): counters and cumulative versus current percentiles.
- [Prometheus histograms and summaries](https://prometheus.io/docs/practices/histograms/): why percentile values cannot be pooled like counts.
- [Google SRE: implementing SLOs](https://sre.google/workbook/implementing-slos/): good/total event ratios.
- [NIST bootstrap](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/bootfit.htm): resampling independent experimental units when repeats exist.

## Current reporting and denominators

Normal grading writes five CSVs in `csvs/`, per-run JSON/Markdown/cache files,
and `logs/grader.log`. See [metrics.md](metrics.md) for their contents. There is
no automatically generated aggregate research summary or paper-metrics file.

Scenario-table maxima/means use evaluable succeeded and failed job scores within
each run; remediation scores include penalties. Session counts include all jobs,
not only scored jobs. Means exclude unavailable/judge-failed scores. Keep runs
as experimental units when performing additional campaign-level aggregation;
do not let runs with more retries receive more weight accidentally.

Top-level `graded`, job `succeeded`, semantic alignment and operational recovery
are separate concepts. A startup-failed run can still be `graded` with empty
job lists and unavailable windows. Current remediation success records output
completion, not verified recovery. Legacy per-job metric/final-grade fields stay
`not_evaluable`; use `research.operational` for the run-level recovery proxy.

## Paired front-end scenario table

`csvs/scenario_table.csv` contains 18 columns: the twelve scenario/score/baseline/best-window/session fields,
three worst-window fields (P95, paired 5xx, UTC location), and three 5xx
imputation counts. Each row is one
archived run, with maximum and mean scored-job outputs and exported session
counts. Failed jobs with scores are included; remediation totals include
penalties. Missing/judge-failed scores are excluded from means, not replaced with
zero. Job CSVs expose scored counts; per-run JSON retains run identities and provenance.

Use the selected entry point (default `front-end`, unambiguous namespace).
Baseline is the recorded baseline minus the first five minutes by default,
configurable via `--baseline-ignore-minutes`; 0 restores the full baseline.
For a 30-minute baseline, this means minutes 5–30. Measure P95 and 5xx separately
with right-endpoint time integration, two finite nonnegative samples and 90%
coverage. Each sample supports at most one scrape step. P95 is a time average of
workload P95 estimates, not pooled client P95; 5xx is requests/second.

Independently scan the full recorded chaos intervals, using complete five-minute
windows by default at the recorded scrape step. No window crosses idle gaps or
cleanup boundaries. Remediation/RCA job timing never restricts these windows.
For a one-hour interval and 15-second step there are 221 candidate windows.
Both metrics must meet coverage in the same window. Best is minimum mean P95
subject to mean 5xx <= 0.5 requests/s. Worst is maximum mean P95 across all covered
windows, without the ceiling; it can remain available when best is unknown.
Ties select earliest time. Record both metric values at each selected location.

Baseline eligibility does not gate chaos-window selection. An empty trimmed
baseline or missing baseline 5xx leaves that baseline value unknown but preserves
valid best/worst chaos measurements. `paired_window` records the exclusion,
threshold, boundaries, selection rules, coverage and unknown reasons. This
additive report preserves schema 2, recovery scoring and the older independent
per-workload full-baseline comparisons.

## Notebook output contract and explicit 5xx imputation

The current CLI writes only `runs/`, `logs/grader.log` and five CSVs under `csvs/`:
summary, RCA rubric scores, remediation rubric scores, window comparison and
scenario table. Aggregate incident, paper-metrics and research-summary
artifacts are retired from normal generation;
existing historical files remain intact. Per-run schema-2 JSON retains evidence.

By explicit user request, descriptive window calculations now impute an absent
HTTP 5xx sample as zero at a matching finite recorded traffic timestamp for the
same namespace/workload. This includes an absent workload series in a successful
query result matrix. This is an analysis assumption, not a measured absence of
errors. Query files must exist and contain a successful result matrix. Explicit
nonfinite error samples, missing/failed query files and traffic gaps remain
unavailable; no latency or job-score imputation is performed. Both independent
window comparisons and paired front-end selection use the rule. CSVs expose
baseline/selected-window imputed-sample counts, with a policy column in the
window CSV and the policy recorded in per-run paired-window JSON. Recovery
calculations continue using original evidence without this imputation.


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
The notebook applies the same filter to historical grades and exposes excluded
session counts. Historical grade files and judge caches are not rewritten by
notebook execution. Whole-run cumulative client mean/P95 summaries are omitted
from chaos-only metrics.

The effective `policy_hash` hashes both the policy and `time_scope` version, so
chaos-only recovery is not pooled with historical post-chaos recovery.
`source_policy_hash` retains the hash of the unchanged source policy.
