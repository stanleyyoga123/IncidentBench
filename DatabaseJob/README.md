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

Applications perform DML only. DatabaseJob owns its ConfigMap and migration Job
in `kubernetes/`; Infrastructure supplies database credentials, sets the
explicit reset flag, and runs the Job before all services.

For an existing PostgreSQL PVC, changing the Vault password does not update the
stored database role automatically. The Infrastructure database role restarts
the pod on Secret changes and synchronizes that role over PostgreSQL's trusted
local socket before starting this migration Job.

Build and push the development image referenced by `kubernetes/job.yaml`:

```bash
./build.sh
```

The default target platform is `linux/amd64`; override it with `PLATFORM` when
needed. Docker authentication for the `stanleyyoga123` namespace must already
be configured.

Run `pytest -q` and `python -m compileall -q migrations tests` before release.
