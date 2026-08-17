# Infrastructure

`Infrastructure/ansible/site.yml` is the authoritative installation entrypoint.
It provisions k3s/node roles, observability, Chaos Mesh/chaosd, PostgreSQL,
migrations, agent services, network probes, and the optional evaluation runner.

Application resources are owned beside their code in
`AnomalyDetector/kubernetes/manifest.yaml`,
`AgentOrchestrator/kubernetes/manifest.yaml`, `RCAAgent/kubernetes/manifest.yaml`,
`RemediatorAgent/kubernetes/manifest.yaml`, and `MCPTools/kubernetes/`.
Infrastructure applies those manifests and owns the shared
`kubernetes/agents/shared.yaml` NetworkPolicy. MCPTools owns its split service
accounts, read/remediation RBAC, remediation artifact PVC, and overlay/underlay
probe DaemonSets.

Deployment order is enforced by roles:

1. PostgreSQL readiness and Alembic migration;
2. both MCPTools deployments;
3. RCAAgent and RemediatorAgent;
4. AgentOrchestrator;
5. AnomalyDetector ingestion.

Runtime `.env` files are rendered into Kubernetes Secrets from Ansible Vault
variables. Do not commit rendered Secrets or real token values.
