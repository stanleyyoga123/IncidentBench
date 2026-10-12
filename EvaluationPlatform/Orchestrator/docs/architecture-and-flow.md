# EvaluationOrchestrator architecture

EvaluationOrchestrator owns persistence and the Runner-facing evaluation API.
It does not trigger agents, poll job services, or run reconciliation loops.
Those responsibilities belong to `Agents/Orchestrator`.

The persistence repository exposes existing submitting states for response-loss
recovery. It also uses its injected database connection for workflow reads.
These changes require no table, column or stored-result conversion.

## Existing persistence contracts

RCAAgent, RemediatorAgent and LearningAgent call the unchanged
`/api/v1/internal/...` job APIs to create/read jobs, claim/renew the singleton
execution slot, checkpoint output, finish jobs, and record audits/artifacts.
`AGENT_STORE_TOKEN` authenticates those requests. The existing transaction logic
preserves retries, terminal remediation failure, schema-validated lesson
publication, idempotency, output retention and namespace isolation.

AgentOrchestrator calls authenticated internal orchestration persistence APIs
for anomaly ingestion, pending-event claims, workflow reads/transitions, job
attachment, lesson retrieval and bounded source audit retrieval. Lifecycle
policy remains in AgentOrchestrator; all SQL writes remain here.

Lesson read/enable/disable routes remain here under `/api/v1/lessons`, using
`AGENT_CONTROL_TOKEN`. Workflow controls and detector ingestion are hosted by
AgentOrchestrator. See each service's OpenAPI and [API reference](agent-api.md).

## Evaluation and cross-service maintenance

Runner calls this service for acquire, pause, resume, reset, export and release.
The `evaluation_control` singleton and advisory lock retain their existing
semantics. Each mutation takes a shared lock and rejects maintenance. Evaluation
transitions take the exclusive lock; exports use the existing repeatable-read
snapshot. AgentOrchestrator holds the same shared lock across dispatch using a
read-only PostgreSQL transaction. A transition waits for dispatch to finish and
cannot interleave reset with a downstream submission. Nonblocking shared lock
acquisition avoids nested submission deadlocks.

No migrations or DDL are introduced. Export remains schema version 1 with six
arrays: `anomaly`, `rca_session`, `remediation_run`, `remediation_session`,
`learning_session` and `workflow`. Runner's archive and Grader input contracts
remain unchanged. A service outage does not prevent offline grading of archives.

## Deployment

The service/image is `evaluation-orchestrator`; namespace remains `agents`.
Its Secret contains database, control and store credentials only. AgentOrchestrator's shared
NetworkPolicy permits agent services and the lifecycle orchestrator to reach
store APIs; this service's policy permits Runner on the evaluation HTTP port. DatabaseJob
remains the sole DDL owner. The service uses the existing database without
conversion or reset during this split.
