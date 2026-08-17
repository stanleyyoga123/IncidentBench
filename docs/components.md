# Components

| Component | Owns | Does not own |
| --- | --- | --- |
| AnomalyDetector | Prometheus queries, adaptive profiles, event envelopes, HTTP delivery | PostgreSQL or workflow state |
| AgentOrchestrator | ingestion, deduplication, batching, workflows, approvals, retries | LLM reasoning or cluster tools |
| RCAAgent | asynchronous RCA, evidence, sub-agent spawning, RCA audit | remediation execution |
| RemediatorAgent | approved execution, verification, changes/artifacts audit | approval policy or detector tuning |
| MCPTools | kubectl, Prometheus, Loki, Jaeger, network, baseline, Ansible artifacts/execution | workflow DML |
| Orchestrator | Alembic schema versioning | long-running coordination |
| Infrastructure | Ansible, nodes, charts, manifests, secrets, RBAC, probes | experiment-time restarts |
| Evaluation | experiments, restarts, scale/wait, cleanup, artifacts | installation |

API entry points are `/api/v1/anomalies`, `/api/v1/workflows`,
`/api/v1/rca/jobs`, `/api/v1/remediation/jobs`, and `/mcp`. Each HTTP service
also exposes `/health`; FastAPI services publish OpenAPI at `/docs`.
