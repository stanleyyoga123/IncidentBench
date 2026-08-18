# Components

| Component | Owns | Does not own |
| --- | --- | --- |
| AnomalyDetector | detection, delivery, ConfigMap, Secret, workload manifest, deploy script | PostgreSQL or workflow state |
| AgentOrchestrator | workflows/approvals, all application DML, ConfigMap, Secret, NetworkPolicy, workload manifest, deploy script | LLM reasoning or cluster tools |
| RCAAgent | asynchronous RCA, ConfigMap, Secret, workload manifest, deploy script | PostgreSQL DML or remediation execution |
| RemediatorAgent | approved execution/verification, ConfigMap, Secret, workload manifest, deploy script | PostgreSQL DML, approval policy, or detector tuning |
| MCPTools | cluster tools, profile Secrets/manifests, RBAC, PVC, probes, deploy script | workflow DML |
| DatabaseJob | PostgreSQL, Secret, Compose, Alembic schema/migration Job, deploy script | long-running coordination |
| Infrastructure | cluster/node Ansible, platform namespaces/tools, Helm values | application/database/evaluation deployment or Secrets |
| Evaluation | experiments, restarts, cleanup, artifacts, runner Secret/Ansible/deploy script | platform installation |

API entry points are `/api/v1/anomalies`, `/api/v1/workflows`,
`/api/v1/rca/jobs`, `/api/v1/remediation/jobs`, and `/mcp`. Each HTTP service
also exposes `/health`; FastAPI services publish OpenAPI at `/docs`.

Every committed `kubernetes/secret.example.yml` uses `++++++++` placeholders.
Copy each example to ignored `kubernetes/secret.yml` without committing it;
deploy scripts refuse required placeholders and use kubectl's current context.
