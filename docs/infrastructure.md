# Infrastructure

`Infrastructure/ansible/site.yml` is the authoritative installation entrypoint.
It provisions k3s/node roles, observability, Chaos Mesh/chaosd, PostgreSQL,
migrations, agent services, network probes, and the optional evaluation runner.

Application ConfigMaps and workload resources are owned beside their code in
each component's `kubernetes/` directory. Infrastructure applies those
manifests and owns the shared
`kubernetes/agents/shared.yaml` NetworkPolicy. MCPTools owns its split service
accounts, read/remediation RBAC, remediation artifact PVC, and overlay/underlay
probe DaemonSets.

Deployment order is enforced by roles:

1. database and service credential Secrets;
2. PostgreSQL readiness, password synchronization, and Alembic migration;
3. both MCPTools deployments;
4. RCAAgent and RemediatorAgent;
5. AgentOrchestrator;
6. AnomalyDetector ingestion.

Each component ConfigMap supplies the non-secret `/app/.env` file. Ansible
Vault values are rendered only into credential Secrets and injected into the
container for the `${VARIABLE}` references in that file. Do not put passwords,
tokens, or database DSNs in ConfigMaps.

To apply or rotate only the Kubernetes runtime Secrets, without deploying any
application, run:

```bash
cd Infrastructure/ansible
ansible-playbook playbooks/secrets.yml --ask-vault-pass -e @vault.yml
```

After a database password rotation, run the database phase as well. PostgreSQL
stores its role password in the persistent data volume, so changing only the
Kubernetes Secret does not update the existing database role.
