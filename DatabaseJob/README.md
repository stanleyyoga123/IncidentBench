# DatabaseJob schema project

This directory is the sole owner of PostgreSQL DDL for the split agent
platform. It contains Alembic migrations and a migration image; it is not a
long-running coordination service.

Head revision `20260817_0002` replaces the legacy CloudAgent tables with:

- `anomaly_event`, `agent_workflow`, `rca_job`, `remediation_job`;
- singleton `agent_execution_slot` for global RCA/remediation serialization;
- `agent_tool_call` and `remediation_artifact` audit tables.

The upgrade is intentionally destructive. When any legacy table has records,
it refuses to proceed unless `ALLOW_AGENT_WORKFLOW_RESET=true` is supplied.
Downgrade recreates legacy structures only; deleted data is unrecoverable.

```bash
export DATABASE_URL='postgresql://user:password@localhost:5432/database'
export ALLOW_AGENT_WORKFLOW_RESET=true  # coordinated reset only
alembic upgrade head
```

Applications perform DML only. DatabaseJob independently owns
`kubernetes/postgres.yaml`, `kubernetes/secret.yml`,
`kubernetes/configmap.yaml`, `kubernetes/job.yaml`, `compose/database.yml`, and
`deploy.sh`. Infrastructure does not provision PostgreSQL or run migrations.

For Kubernetes, replace all three `++++++++` values in
`kubernetes/secret.yml`, select the intended kubectl current context, and run:

```bash
ALLOW_AGENT_WORKFLOW_RESET=true ./deploy.sh  # destructive coordinated reset
```

Omit the variable (or set it to `false`) for normal additive migrations. The
script refuses placeholders, scales a detected legacy CloudAgent and
AnomalyDetector down before an explicitly authorized reset, applies PostgreSQL,
waits for readiness, and runs the migration Job. For an existing PVC, changing
the Secret does not update PostgreSQL's persisted role automatically; the
script rolls the StatefulSet and synchronizes the role password over its local
socket before migration. It withholds migration pod logs because they may
contain sensitive values.

Build and push the development image referenced by `kubernetes/job.yaml`:

```bash
./build.sh
```

The default target platform is `linux/amd64`; override it with `PLATFORM` when
needed. Docker authentication for the `stanleyyoga123` namespace must already
be configured.

For a local database, copy `.env.example` to the ignored `.env`, replace every
placeholder, then run from this directory:

```bash
docker compose --env-file .env -f compose/database.yml up -d postgres
docker compose --env-file .env -f compose/database.yml run --rm migration
```

Run `pytest -q` and `python -m compileall -q migrations tests` before release.
