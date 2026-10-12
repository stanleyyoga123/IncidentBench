# EvaluationOrchestrator

EvaluationOrchestrator is the sole application database writer. It retains the
existing RCA, remediation and learning job-store APIs, leases, output checkpoints,
tool audits, artifacts, lessons, evaluation ownership/reset and session exports.
Agent triggering and lifecycle coordination live in
[`Agents/Orchestrator`](../../Agents/Orchestrator/README.md).

The ClusterIP service is `evaluation-orchestrator` in namespace `agents`, port
8080. Runner's `orchestrator_url` and the three job services' `orchestrator.base_url`
point here. Internal APIs use `AGENT_STORE_TOKEN`; evaluation and lesson controls
use `AGENT_CONTROL_TOKEN`. This service has no downstream agent credentials,
agent clients, or dispatch threads.

The split does not change the database schema, job/output payloads, export SQL,
or archive format. Existing databases and archived experiments remain usable.
Do not run a reset or a migration merely to install this split. Full run archives
remain owned by Runner, including its existing optional S3 upload.

## Runtime ownership

- `app/features/evaluation/`: evaluation HTTP routes, ownership and maintenance,
  reset and repeatable-read session exports.
- `app/features/agent_workflow/`: existing job/workflow persistence, internal
  store APIs and lesson APIs. Internal orchestration endpoints expose persistence
  operations to AgentOrchestrator without moving DML out of this service.
- `app/infrastructure/`: database, authentication, and shared maintenance locking.
- `../Database/`: unchanged PostgreSQL deployment and Alembic migrations; sole DDL owner.

Evaluation maintenance waits for the existing advisory lock held by active
AgentOrchestrator dispatch and store mutations. Both services use the same
PostgreSQL database and lock identity. Reset/export continue to require ownership
and maintenance. Both orchestrators stay running during evaluation baseline.

## Configuration and deployment

Copy `.env.example` to ignored `.env` for local use, install `requirements.txt`,
and run `./run.sh`. OpenAPI is available at `/docs`.

Copy `kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml` and replace
placeholders locally. Set `IMAGE_REGISTRY` and `IMAGE_TAG` for `./build.sh` and
`./deploy.sh`. The deployment script uses kubectl's current context. It never
runs migrations. Follow the [split cutover](../../docs/operations.md#orchestrator-split-cutover)
for an existing deployment.

See [evaluation API](docs/evaluation-api.md), [store API](docs/agent-api.md), and
[architecture](docs/architecture-and-flow.md).
