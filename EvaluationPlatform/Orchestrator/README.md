# AgentOrchestrator

AgentOrchestrator accepts authenticated AnomalyDetector events, persists them,
and coordinates asynchronous RCA, remediation, and post-workflow learning jobs.
It is the only application that talks to PostgreSQL: workflow rows, RCA and
remediation/learning jobs, incident lessons, the singleton execution slot,
tool-call audits, and remediation artifacts. It polls pending events every 60
seconds and batches at most 100 into one workflow. RCA, remediation, and
learning share the single execution slot.

Detailed documentation starts at [`docs/README.md`](docs/README.md), including
the complete ingestion, workflow, downstream trigger, lease, and lesson flow.

Run DatabaseJob migrations before starting. Copy `.env.example` to `.env`,
then run `./run.sh`. OpenAPI is available at `/docs`.

This component owns its ConfigMap, placeholder Secret, NetworkPolicy,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. Match `AGENT_INGESTION_TOKEN` with
AnomalyDetector, `AGENT_STORE_TOKEN` with all three job services,
`RCA_SUBMIT_TOKEN` with RCAAgent, `REMEDIATOR_SUBMIT_TOKEN` with RemediatorAgent,
and `LEARNING_SUBMIT_TOKEN` with LearningAgent; keep `AGENT_CONTROL_TOKEN`
independent. Deploy after both MCP profiles and all three job services.

## Evaluation control

The bundled Runner uses authenticated [evaluation APIs](docs/evaluation-api.md)
for durable serial ownership, maintenance, full reset and consistent session export.
Orchestrator remains available while configured workers are stopped. Database
deployment and additive migrations live in `Database/`; runtime code remains DML-only.
