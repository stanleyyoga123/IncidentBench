# DatabaseJob schema ownership and migration flow

## Purpose and boundary

DatabaseJob is the sole DDL owner for the platform PostgreSQL database. It
packages Alembic migrations and runs them locally, through Compose, or as a
Kubernetes Job. It is not a long-running API or workflow coordinator.

AgentOrchestrator is the only runtime application that performs DML. The three
agent services persist through AgentOrchestrator's internal HTTP API. No agent
service should import Alembic, create tables at startup, or carry a database
DSN.

## Migration chain

```text
<base>
  -> 20260817_0001  adopt/create legacy anomaly workflow schema
  -> 20260817_0002  destructive split-agent schema replacement
  -> 20260819_0003  additive learning jobs and incident lessons
  -> 20260831_0004  anomaly and lesson namespace scope (head)
```

Alembic must report one head: `20260831_0004`.

## Coordinated migration sequence

```mermaid
sequenceDiagram
  participant Op as Operator/deploy.sh
  participant K as Kubernetes
  participant P as PostgreSQL
  participant J as Database migration Job
  participant A as Agent services

  Op->>K: verify current context and Secret placeholders
  Op->>K: apply PostgreSQL resources
  Op->>P: wait ready and synchronize persisted role password
  Op->>K: create migration Job
  J->>P: alembic upgrade head
  P-->>J: commit schema revision
  J-->>Op: completed
  Op->>A: deploy Learning/RCA/Remediator/Orchestrator/Detector in order
```

For the incompatible legacy reset, old agent and detector writers must be
scaled down before the migration. Use `ALLOW_AGENT_WORKFLOW_RESET=true` only
for that coordinated operation.

## Revision 0001: legacy adoption

The initial revision can create the former tables or adopt a compatible
existing schema. Adoption inspects expected table/column structure and refuses
an incompatible partial schema instead of silently stamping it. This revision
exists so older research databases can enter Alembic history consistently.

## Revision 0002: split-agent schema

Revision `20260817_0002` replaces five legacy workflow/audit tables with the
API-service schema. Before dropping anything, it inspects each legacy table and
counts rows. If any is non-empty, migration fails unless the environment value
`ALLOW_AGENT_WORKFLOW_RESET` is `1`, `true`, or `yes`.

Offline SQL generation skips the live row-count gate because it cannot inspect
data. Applying generated SQL remains an operator-controlled destructive action.

The revision creates:

### `agent_workflow`

One durable orchestration unit for a batch. It stores status/version, RCA and
remediation job references, decision actor/reason, errors, and lifecycle
timestamps. Later revision 0003 adds learning reference/status/error.

### `anomaly_event`

One detector envelope. `event_id` is globally unique for idempotent ingestion.
It stores optional namespace, detection scope, method/detail, profile
provenance, original JSONB payload, processing status, optional workflow FK,
and timestamps. Pending indexes support oldest-event intake and namespace-
isolated workflow batching.

### `rca_job`

Durable asynchronous RCA request/result/raw output/error, unique idempotency
key, workflow relation, status/version, attempts, lease owner/expiry, and
timestamps.

### `remediation_job`

Durable approved remediation with the same job fields plus a restrictive FK to
its RCA job. Remediation failures can be represented as `needs_review` because
mutation state may be ambiguous.

### `agent_execution_slot`

Exactly one row, enforced by `CHECK (id = 1)`. Holder type/job, lease owner,
expiry, and update time serialize RCA, remediation, and later learning work.

### `agent_tool_call`

Append-only service/job/tool arguments/result/outcome audit. The generic job ID
allows RCA and remediation calls in one table; application logic supplies the
service discriminator.

### `remediation_artifact`

Durable job-scoped filename/content/SHA-256 with unique job+filename. MCPTools
also stores files on a PVC, but this table preserves the workflow audit.

## Revision 0003: learning and lessons

Revision `20260819_0003` is additive. It adds workflow learning columns,
`learning_job`, and `incident_lesson`. It also repairs the singleton execution
slot with `INSERT ... ON CONFLICT DO NOTHING`.

### `learning_job`

One job per workflow, enforced by unique `workflow_id`. It uses the same durable
request/result/raw/error, attempts, lease, version, and timestamp pattern as
RCA. Deleting the source workflow cascades to its learning job.

### `incident_lesson`

Multiple ordered lessons may belong to one learning job. The unique
`(learning_job_id, ordinal)` constraint makes publication idempotent while
retaining model order. Each row stores category, title, guidance, applicability,
avoidance guidance, evidence references, optional
namespace/resource/name/metric scope, tags, confidence, active flag,
optimistic version, status actor/reason, and timestamps.

## Revision 0004: workload namespace scope

Revision `20260831_0004` adds nullable `namespace` columns to `anomaly_event`
and `incident_lesson`, backfills anomaly namespaces from retained JSONB, and
rebuilds scope indexes. Cluster-scoped node evidence and lessons keep a null
namespace; namespaced deployment evidence must carry its exact namespace.

Confidence is constrained to 0–1; ordinal is non-negative; versions are
positive. Indexes support active scope/recency retrieval and confidence review.

## Relationship overview

```mermaid
erDiagram
  AGENT_WORKFLOW ||--o{ ANOMALY_EVENT : groups
  AGENT_WORKFLOW ||--o| RCA_JOB : references
  RCA_JOB ||--o{ REMEDIATION_JOB : authorizes
  AGENT_WORKFLOW ||--o| REMEDIATION_JOB : references
  AGENT_WORKFLOW ||--o| LEARNING_JOB : learns
  LEARNING_JOB ||--o{ INCIDENT_LESSON : publishes
  AGENT_WORKFLOW ||--o{ INCIDENT_LESSON : source
  REMEDIATION_JOB ||--o{ REMEDIATION_ARTIFACT : owns
```

`agent_tool_call` is logically associated by service/job ID. The singleton
execution slot points to one active job identity but intentionally does not use
a polymorphic FK.

## Runtime transaction invariants

The schema supports, while AgentOrchestrator enforces:

- event acknowledgement only after commit;
- idempotency through unique event/job keys;
- optimistic workflow/lesson versions;
- one active execution lease globally;
- safe RCA/learning retry and remediation `needs_review`;
- atomic learning success, lesson publication, and slot release;
- cascade cleanup of workflow learning data and remediation artifacts.

Database constraints complement but do not replace API transition validation.

## Kubernetes resources

DatabaseJob owns:

- PostgreSQL StatefulSet/Service/storage manifest;
- component ConfigMap and placeholder Secret;
- migration Job manifest;
- build and deployment scripts.

`kubernetes/job.yaml` uses the DatabaseJob image to run Alembic. Application
deployments should start only after the Job completes. Infrastructure installs
cluster prerequisites but does not run database migrations.

The ignored `kubernetes/secret.yml` must contain matching PostgreSQL database,
user, and password values. For an existing PVC, changing the Kubernetes Secret
does not automatically change the persisted PostgreSQL role password;
`deploy.sh` synchronizes the role via the local socket before migration.

## Local and offline workflows

Local migration:

```bash
export DATABASE_URL='postgresql://user:password@localhost:5432/database'
alembic upgrade head
```

Inspect generated PostgreSQL SQL without applying:

```bash
alembic upgrade head --sql
alembic downgrade 20260819_0003:20260817_0002 --sql
```

The tests use offline SQL to verify one head, table creation, constraints,
foreign keys, lesson indexes, singleton repair, and additive downgrade shape.

## Downgrade semantics

Downgrading 0003 removes lessons/learning jobs and workflow learning columns,
returning to the split-agent schema. Downgrading through 0002 recreates legacy
table structure only. Records destroyed during the authorized upgrade are not
recovered.

Never present downgrade as a data restore. Back up data separately when it must
survive an incompatible rollout.

## Evaluation cleanup/export interaction

Evaluation pre-run truncates all current runtime tables, including
`incident_lesson` and `learning_job`, in one statement, then clears—but does not
truncate—the singleton slot. Including the learning tables is required by FK
relationships even when they appear empty.

Evaluation post-run exports learning jobs with ordered nested lessons before the
next pre-run cleanup. This preserves run evidence while isolating subsequent
experiments.

## Troubleshooting

- `password authentication failed`: compare DatabaseJob Secret values,
  persisted role password, and AgentOrchestrator `DATABASE_DSN`; rerun the
  password synchronization path rather than regenerating unrelated Secrets.
- Migration refuses reset: legacy tables contain data; stop writers, back up as
  required, and explicitly set the reset flag only for the coordinated reset.
- Missing table/column at runtime: verify `alembic current` and head before
  restarting applications.
- Multiple Alembic heads: stop rollout and reconcile migration history; do not
  stamp arbitrarily.
- Migration Job crash: inspect Job events/status and sanitized logs; avoid
  printing the DSN.
- Evaluation TRUNCATE FK error: ensure every referencing runtime table from the
  current head is included in the same TRUNCATE statement.
- Execution slot row absent: apply through the current head; revision 0003's repair insert is
  idempotent.

## Source map

| File | Responsibility |
| --- | --- |
| `alembic.ini` | Alembic project configuration. |
| `migrations/env.py` | Database URL and migration execution mode. |
| `migrations/versions/20260817_0001_initial_schema.py` | Legacy create/adopt baseline. |
| `migrations/versions/20260817_0002_agent_services.py` | Destructive split-agent replacement. |
| `migrations/versions/20260819_0003_learning_lessons.py` | Additive learning schema and slot repair. |
| `migrations/versions/20260831_0004_namespace_scope.py` | Namespace scope for anomaly events and lessons. |
| `kubernetes/job.yaml` | In-cluster migration execution. |
| `deploy.sh` | Context/Secret validation, PostgreSQL readiness/password sync, Job run. |
| `tests/test_migrations.py` | Migration and destructive-guard contracts. |
