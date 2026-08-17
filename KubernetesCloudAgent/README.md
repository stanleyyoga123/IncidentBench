# Kubernetes Cloud Agent

> **Retired deployable.** This directory is retained as migration history only.
> Production responsibilities now belong to `../AgentOrchestrator/`,
> `../RCAAgent/`, `../RemediatorAgent/`, and `../MCPTools/`. Infrastructure no
> longer deploys this worker; do not start it against migration head
> `20260817_0002` because its legacy tables have been removed.

## Legacy behavior (pre-20260817_0002 only)

This worker consumes AnomalyDetector signals from PostgreSQL, performs
evidence-backed Kubernetes RCA, optionally remediates the cluster, and records
the completed session.

Database schema ownership is centralized in `../Orchestrator`. The worker does
not create workflow or remediation tables at runtime. Run `alembic upgrade
head` through the Orchestrator before starting this service.

```bash
cd ../Orchestrator
DATABASE_URL='postgresql://user:password@localhost:5432/database' ./run.sh
```

Then configure `KubernetesCloudAgent/.env` and start the worker:

```bash
cd ../KubernetesCloudAgent
./run.sh
```

The detector and cloud agent must use the same PostgreSQL database. See the
root `docs/` directory for architecture, data contracts, and deployment order.
