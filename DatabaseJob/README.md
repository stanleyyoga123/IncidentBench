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

Applications perform DML only. PostgreSQL installation and the migration Job
are owned by `../Infrastructure/`, which orders migration before all services.

Run `pytest -q` and `python -m compileall -q migrations tests` before release.
