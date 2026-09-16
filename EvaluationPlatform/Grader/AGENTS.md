# Project instructions for coding agents

## Mission and scope

This machine hosts the standalone offline Grader workspace at
`/user/stefanusstan/Evaluation`. It evaluates archived Kubernetes incident runs,
grades final RCA/remediation results, and produces research reports and charts.
The rest of the incident platform lives on the user's laptop.

The upstream flow is Evaluation -> detection -> orchestration -> RCA ->
remediation -> verification -> learning. Here, that flow is context for archived
inputs, not a set of services to implement or deploy. Do not assume sibling
Runner, Agents, Orchestrator, or Database directories exist. Describe any needed
upstream contract change explicitly; implement only the local part available here.
A deeper `AGENTS.md` supplies instructions for its subtree.

Before changing grading behavior, read `README.md`, `grader/README.md`,
`docs/evidence-contract.md`, `docs/methodology.md`, and `docs/metrics.md`.
For plotting changes, also read `visualizer/README.md`. Some documentation paths
still describe the full upstream repository; resolve local paths from this root.

## Ownership and layout

- `grader/cli.py`, `pipeline.py`: configuration, discovery, validation, job grading,
  concurrency, checkpoints, and report orchestration.
- `grader/judge.py`, `rubric.py`, `penalty.py`, `ground_truth.py`: semantic payloads,
  structured classifications, deterministic scoring, and reference loading.
- `grader/archive_metrics.py`, `metrics.py`, `window_comparison.py`: archive-derived
  measurements, telemetry summaries, and baseline/chaos comparisons.
- `grader/research.py`, `calibration.py`, `research_reports.py`, `reports.py`:
  optional richer evidence, calibration, aggregation, and output formats.
- `visualizer/`: archive metric loading, lifecycle timelines, and rendering.
- `analyzer.py`: analysis of existing run archives and grading outputs.
- `resources/`: authoritative rubric, evaluation policy, scenario policy,
  manually maintained ground truth, and scenario penalties.
- `tests/`: offline regression tests; `docs/`: contracts and methodology.
- `results/`: source archives. `grades/` and `visualizations/`: generated outputs
  and historical reports. Preserve their existing contents.

## Evidence and grading invariants

1. Treat source archives as immutable. Read archive-relative files; do not follow
   old metadata endpoints, execute archived hooks/scripts, or alter captured data.
2. Original Runner archives remain sufficient for `archive-recovery-v3`.
   Optional `evidence/` records must not become mandatory. Do not require new
   telemetry, scenarios, paired runs, or longer experiments for ordinary grading.
3. Missing, malformed, nonfinite, reset, or insufficiently covered measurements
   remain explicitly unknown/unevaluable. Do not replace missing evidence with
   zero, success, prose claims, job timestamps, or configured durations.
4. Keep the archive service recovery proxy separate from semantic quality,
   verified actions, safety, active-fault recovery, and causal benefit. Job or
   tool success does not prove applied remediation or safe recovery.
5. Derive client failure ratios and successful throughput from actual cumulative
   Locust counter differences and measured time. Cumulative CSV percentiles do
   not establish interval client P95. Assess baseline-active services separately;
   healthy services must not conceal harmed or disappearing services.
6. Preserve recorded incident boundaries, coverage checks, recovery streaks,
   cleanup-phase labels, and visible invalid/insufficient/no-degradation outcomes.
   Keep denominators and measurement bases explicit. Runs, not jobs or scrape
   samples, are the experimental reporting units.
7. Sliding comparisons use the full recorded baseline and complete windows within
   individual recorded chaos intervals, before cleanup. Select best/worst per
   metric and workload, preserve coverage checks and earliest-time tie breaking,
   and keep these descriptive comparisons separate from recovery scoring.
8. Only succeeded jobs with non-empty final `result` receive semantic judging.
   Preserve failed, running, result-less, and judge-failed jobs with explicit
   dispositions. Missing required inputs mark the affected run ungraded while
   other runs continue. `--operational-only` must make zero model calls.
9. Normal semantic payloads use scenario, ground truth, final result, and bounded
   portable observations. Do not add private reasoning or raw tool traces.
   Archived chaos manifests belong in validation and the separate remediation
   penalty call, not the normal rubric call. Synthetic-fault terminology itself
   is neither required nor rewarded.
10. `resources/rubric.json` owns criterion classes, scores, and weights. The judge
    classifies; Python computes scores. Penalties apply only to remediation,
    subtract from the rubric score, and floor at zero. Alignment is independent
    of penalties. Do not generate or overwrite ground truth during grading;
    edit reference files only when the task calls for it.
11. Preserve atomic, content-addressed judge checkpoints and independent penalty
    caching. Changes to prompts or grading inputs must invalidate affected cache
    entries. Record policy/methodology and hashes so results remain reproducible.
12. Preserve schema version 2 and established JSON/CSV fields unless the task
    explicitly changes the contract. Trace report, analyzer, visualizer, cache,
    and test consumers before changing fields, statuses, resource paths, or CLI
    options. Document intentional contract and methodology changes together.

## Development and data handling

- Make focused changes and preserve unrelated files. Check Git status if this
  checkout has Git metadata; do not assume that a copied workspace is a repository.
- Select a fresh output directory for grading or visualization experiments so
  historical reports and caches remain available for comparison.
- Keep default resource paths relative to the source tree, independent of the
  working directory. Support explicit CLI overrides.
- Mock model and HTTP boundaries in tests. Routine validation is offline; ordinary
  semantic grading contacts the configured OpenAI-compatible judge endpoint.
- Keep tokens, model keys, DSNs, kubeconfigs, private keys, and populated `.env`
  values out of logs, responses, commits, and generated artifacts. Do not assume
  `.env` is ignored without checking the actual repository configuration.
- Logs may report identifiers, hashes, outcomes, and validation reasons; do not
  log prompts, reference/manifest bodies, final result contents, raw model output,
  reasoning, tool traces, or learning data.
- Live deployment, remediation, chaos, cluster cleanup, installation, and database
  migrations are outside this workspace's grading role. They require an explicit
  user request and a confirmed target; offline grading requires neither.

## Commands and verification

Run from this workspace root. Use the existing `.venv` when available; install
`requirements.txt` and `pytest` only if the selected environment needs them.
Use `python` below from that environment.

```bash
# Focused suites: select those affected by the change.
python -m pytest -q tests/test_grader.py
python -m pytest -q tests/test_archive_metrics.py tests/test_research.py tests/test_window_comparison.py
python -m pytest -q tests/test_visualizer.py

# Full local suite after implementation changes.
python -m pytest -q
python -m compileall -q grader visualizer analyzer.py

# Example offline assessment: choose a fresh output path for each experiment.
python -m grader --input results/sock-shop-1 --output grades/my-offline-check --operational-only
python -m visualizer --input results/sock-shop-1 --output visualizations/my-check
```

Prefer direct module invocations for configurable runs. The current `grade.sh`
hard-codes arguments and does not forward extra CLI arguments; do not rely on
`./grade.sh --operational-only` to disable judge calls. Check its implementation
before using it. Likewise, pass explicit local paths to `analyzer.py` rather
than relying on its historical sibling-Runner defaults.

For measurement changes, use small hand-calculated fixtures covering boundaries,
gaps, resets, missing services, and denominators. For pipeline changes, check
zero judge calls in operational-only mode and deterministic offline outputs.
For schema changes, verify downstream reports and analysis. Do not run unrelated
upstream suites or live infrastructure checks. Documentation-only edits need a
content/path review, not model grading or a full archive rerun.

Report what changed, checks actually performed, and any unavailable dependencies
or remaining limitations. Historical validation counts in `docs/validation.md`
are context, not evidence that checks passed in this checkout.
