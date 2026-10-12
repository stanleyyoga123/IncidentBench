# AgentOrchestrator instructions

Own detector ingestion, lifecycle decisions, batching, reconciliation, downstream
job submission, automatic remediation approval, decline/retry and learning
submission. Preserve existing payloads, statuses, actor `agent-orchestrator`,
60-second/100-event defaults, hashes, idempotency and bounded lesson context.

All application DML stays in `EvaluationPlatform/Orchestrator`; use authenticated
HTTP persistence endpoints. Direct PostgreSQL access is limited to read-only
maintenance transactions checking `evaluation_control` and holding its existing
shared advisory lock across dispatch. Do not add workflow writes, DDL or schema
migrations. Keep this lock synchronized with EvaluationOrchestrator and preserve
nonblocking nested shared acquisition to avoid deadlocks.

Own component runtime, tests, ConfigMap, placeholder Secret, Deployment/ClusterIP
Service, shared NetworkPolicy and build/deploy scripts. Preserve separate ingestion/control/store
bearer tokens and downstream submission tokens. No real Secret reads or edits.
Both orchestrators remain running during evaluation baseline.

Run `pytest -q` and `python -m compileall -q app tests`; use mock external services.
