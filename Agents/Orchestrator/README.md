# AgentOrchestrator

AgentOrchestrator owns the bundled solution's lifecycle: detector ingestion,
pending-event batching, RCA dispatch, workflow reconciliation, automatic
remediation submission, explicit decline/retry, and learning submission.
Persistence and Runner-facing evaluation APIs live in
[`EvaluationPlatform/Orchestrator`](../../EvaluationPlatform/Orchestrator/README.md).

The ClusterIP service/image remains `agent-orchestrator`, port 8080 in namespace
`agents`. AnomalyDetector keeps its existing URL. Workflow controls retain their
paths, tokens, operation IDs and payloads. Worker job-store clients and Runner
use `evaluation-orchestrator` instead.

## Dependencies

- `store.base_url` / `store.token`: EvaluationOrchestrator's authenticated
  persistence API, using the shared `AGENT_STORE_TOKEN`.
- `rca`, `remediator`, `learning`: existing public job APIs and submission tokens.
- `database.dsn`: same PostgreSQL database as EvaluationOrchestrator, used only
  for read-only maintenance transactions (`SELECT evaluation_control` and the
  existing advisory lock). This service performs no application DML or DDL.
- `api.ingestion_token` and `api.control_token`: detector and workflow-control
  authentication, separate from the persistence token.

The read-only maintenance connection preserves synchronization across the
service split without changing the schema. Evaluation pause waits for active
dispatch; maintenance blocks new dispatch and mutations. Both orchestrators
remain online during baseline. PostgreSQL and EvaluationOrchestrator outages
prevent new durable progress; persisted state remains in the existing database.

Copy `.env.example` to ignored `.env`, install requirements, and run `./run.sh`.
The local example uses port 8084 so EvaluationOrchestrator can use port 8080.
The lifecycle Deployment uses `Recreate` with one replica to prevent overlapping
coordinators during rollout. For Kubernetes, populate the placeholder Secret locally and set `IMAGE_REGISTRY`
and `IMAGE_TAG` before using the component build/deploy scripts.

No migration, archive conversion or experiment rerun is needed. Follow the
[split cutover](../../docs/operations.md#orchestrator-split-cutover) before deploying.
See [lifecycle flow](docs/architecture-and-flow.md) and [HTTP API](docs/agent-api.md).
