# Grader validation guide

## Current checks

Documentation-only updates need a source/path review, not live grading. Compare
CLI defaults in `grader/cli.py`, CSV columns in `reports.py` and
`scenario_table.py`, calculations in `window_comparison.py` and
`archive_metrics.py`, and policy/rubric JSON under `resources/`.

For implementation changes, run from the Grader root:

```bash
python -m pytest -q
python -m compileall -q grader visualizer
```

Focused fixtures include semantic failed-job eligibility, independent and paired
windows, baseline exclusions, explicit 5xx imputation, coverage/gaps, counter
resets, output layout and operational-only behavior. Never overwrite historical
archives or grading outputs when performing an offline assessment.

## Historical validation: 2026-09-15

The following is a dated record, not the current test count, campaign inventory,
or current output-file contract. Several aggregate report files mentioned here
are no longer generated; see [metrics.md](metrics.md).

Validated on 2026-09-15. The Runner research instrumentation, policy/schema
extensions, added CPU paired suites and healthy scenarios were rolled back.
Original scenario catalog remains 76 JSON files; each main application suite
retains its 23 entries. No live cluster operation, Docker build/push or model
request was performed for this change. Unrelated concurrent workspace changes
are preserved.

The original-format synthetic fixture verifies a 300-second baseline with 3000
requests and no failures (10 good requests/s). The incident has 6000 attempts,
120 failures in 600 seconds: 2% failure ratio, 9.8 good requests/s. Per-service
latency exceeds baseline from t=300 to t=420. Four healthy bins 420–540 confirm
proxy recovery at 120 seconds after schedule application, independently of a
job finishing at t=880. Strict observed-fault recovery and slow-request counts
remain null.

Focused fixtures cover traffic collapse, harmed and missing services, missing
intervals, one-sample input, counter resets, baseline failure, no degradation,
failed/repeated jobs, missing cleanup timestamps, fault-phase labelling, derived
5xx missing data, original-format visualization, and a full pipeline with zero
judge calls. Optional richer-evidence tests remain separate from archive-proxy tests.

Required component suites passed: Grader/Runner together 234 tests plus 72
subtests; Detector 38, Orchestrator 27 and Database 11. Detector tests use dummy
localhost settings. Python compileall, diff whitespace, 204 YAML parses, 43 shell
syntax checks and offline Ansible syntax passed. Counts include unrelated
concurrent lock-reset tests; no cluster apply was used.

## Existing archive sample

`../Runner/results/sock-shop-1` contains ten run folders. A real operational-only
report is saved under `grades/sock-shop-1-archive-v3`:

- Three proxy-recovered runs.
- Six proxy-unresolved runs.
- One insufficiently observed run with no completed timing.
- Assessable proxy recovery fraction: 3/9; missing-outcome bounds: [3/10,4/10].

These are descriptive outcomes under this policy, not independently verified
safe recovery or a causal agent-effectiveness estimate. The pass deliberately
skips semantic model classification; job records remain present with explicit
skip reasons. Ordinary grading without `--operational-only` uses the existing
judge-based semantic path.

Identical offline invocations are checked for deterministic incident/report/grade
files and SHA-256 preservation of the original archive files. The analyzer reads
the resulting incident schema. Existing reports outside the new output directory
remain untouched. A new Runner run is not required for this grading method.
