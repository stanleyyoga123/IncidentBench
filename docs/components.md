# Components

| Component | Owns | Does not own |
| --- | --- | --- |
| AnomalyDetector | Prometheus queries, adaptive profiles, event envelopes, HTTP delivery, workload manifest | PostgreSQL or workflow state |
| AgentOrchestrator | ingestion, deduplication, batching, workflows, approvals, retries, workload manifest | LLM reasoning or cluster tools |
| RCAAgent | asynchronous RCA, evidence, sub-agent spawning, RCA audit, workload manifest | remediation execution |
| RemediatorAgent | approved execution, verification, changes/artifacts audit, workload manifest | approval policy or detector tuning |
| MCPTools | kubectl, Prometheus, Loki, Jaeger, network, baseline, Ansible artifacts/execution, profile manifests, RBAC, PVC, probes | workflow DML |
| DatabaseJob | Alembic schema versioning | long-running coordination |
| Infrastructure | Ansible, nodes, charts, shared policy, secrets, component-manifest installation | application workload manifest ownership or experiment-time restarts |
| Evaluation | experiments, restarts, scale/wait, cleanup, artifacts | installation |

API entry points are `/api/v1/anomalies`, `/api/v1/workflows`,
`/api/v1/rca/jobs`, `/api/v1/remediation/jobs`, and `/mcp`. Each HTTP service
also exposes `/health`; FastAPI services publish OpenAPI at `/docs`.
