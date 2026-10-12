# EvaluationOrchestrator instructions

Own all application DML, existing internal RCA/remediation/learning job APIs,
leases, audits, output checkpoints, artifacts, lessons, and evaluation control
and export. Agent lifecycle orchestration lives in `Agents/Orchestrator` and
calls authenticated internal persistence endpoints. Do not add agent clients,
dispatch threads or downstream submission credentials to this service.

Preserve existing tables, data contracts, operation IDs and six export arrays.
This service split introduces no migration, reset or string-only output schema.
Keep `AGENT_STORE_TOKEN` separate from `AGENT_CONTROL_TOKEN`. Database DDL remains
owned only by `../Database/`; runtime code performs DML only.

Preserve deterministic event idempotency, optimistic versions, singleton global
execution, retry limits, output checkpoints and terminal ambiguous remediation
failure. All store mutations use the database maintenance gate. Evaluation
transitions retain the existing exclusive advisory lock; AgentOrchestrator holds
the matching shared lock in a read-only transaction across dispatch. Preserve
ownership/reset idempotency and consistent export snapshots.

Own component ConfigMap, placeholder Secret, Runner ingress NetworkPolicy, Deployment,
ClusterIP Service and build/deploy scripts. Do not read or copy real Secrets.
Run `pytest -q` and `python -m compileall -q app tests` without live services.
