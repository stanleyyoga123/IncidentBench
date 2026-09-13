# Runner instructions

Read README.md, docs/architecture.md, and ../Orchestrator/docs/evaluation-api.md.
Keep experiment settings in versioned JSON; environment files contain deployment
addresses and credential references only. Preserve ordered shell hooks and the
integration lifecycle interface. Never add workflow SQL or database credentials.
Validate before mutations; always finalize and preserve placement comparability.
Run pytest -q, compileall, shell syntax and YAML checks without a live cluster.

Keep engine code and fixed defaults in testbed/, editable experiment inputs in
resources/ and config/, and lifecycle adapters/helpers under hooks/. Operational
scripts live in scripts/. Use the direct Python CLI with --validate-only for
local validation; run.sh executes its configured suite. Grading/analysis code and
outputs belong in ../Grader/. Preserve raw results and historical grade contents.
