# Infrastructure

`Infrastructure/ansible/site.yml` is the authoritative installation entrypoint.
It provisions k3s/node roles, observability, Chaos Mesh/chaosd, PostgreSQL,
migrations, agent services, network probes, and the optional evaluation runner.

Agent resources are in `kubernetes/agents/agent-platform.yaml` and
`anomaly-detector.yaml`. The platform manifest defines split service accounts,
read/remediation RBAC, six ClusterIP workloads, NetworkPolicy, a remediation
artifact PVC, and MCP-owned overlay/underlay probe DaemonSets.

Deployment order is enforced by roles:

1. PostgreSQL readiness and Alembic migration;
2. both MCPTools deployments;
3. RCAAgent and RemediatorAgent;
4. AgentOrchestrator;
5. AnomalyDetector ingestion.

Runtime `.env` files are rendered into Kubernetes Secrets from Ansible Vault
variables. Do not commit rendered Secrets or real token values.
