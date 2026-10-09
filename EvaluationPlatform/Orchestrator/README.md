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

## Code ownership

The service has two feature modules under `app/features/`:

- `evaluation/` owns the Runner-facing HTTP interface, evaluation ownership and
  maintenance transitions, reset, and session export. Its router, service,
  repository, request schema, and export SQL live together.
- `agent_workflow/` owns anomaly ingestion, workflow control, downstream agent
  clients, coordination loops, job persistence, and agent-store HTTP endpoints.

`app/api.py` composes both routers in one FastAPI service. Shared database
connections, bearer authentication, and the maintenance gate live under
`app/infrastructure/`. The gate is injected into agent requests and coordination,
so evaluation maintenance still synchronizes with dispatch and writes without
either feature constructing the other. HTTP paths, tokens, deployment settings,
and Runner hooks remain unchanged.

## Container image

Set `IMAGE_REGISTRY` and `IMAGE_TAG` before using this component's build or
deploy script. For example, `IMAGE_REGISTRY=ghcr.io/my-org` and
`IMAGE_TAG=v1.0.0` produce an image under that registry and tag. The build
script pushes it; the deploy script renders the same reference into the
first-party Kubernetes manifest before applying it. The checked-in
`incidentbench.invalid/*:configure-me` reference is a non-pullable marker.
Third-party images are unaffected.
