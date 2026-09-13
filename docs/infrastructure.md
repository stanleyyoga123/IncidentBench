# Infrastructure

`EvaluationPlatform/Initialization/ansible/site.yml` is the authoritative installation entrypoint.
It provisions k3s/node roles, platform namespaces, observability, Istio,
Chaos Mesh/chaosd, and the restricted node cleaner. It does not deploy
PostgreSQL, migrations, agents, network probes, application Secrets, or the
evaluation runner.

Application ConfigMaps and workload resources are owned beside their code in
each component's `kubernetes/` directory. Components also own their placeholder
Secrets and default-current-context deploy scripts. AgentOrchestrator owns
`kubernetes/network-policy.yaml`; MCPTools owns its split service accounts,
RBAC, remediation artifact PVC, and overlay/underlay probe DaemonSets.

Operators preserve this deployment order:

1. run Infrastructure `site.yml` for platform prerequisites;
2. replace DatabaseJob placeholders and run `EvaluationPlatform/Orchestrator/Database/deploy.sh`, using
   `ALLOW_AGENT_WORKFLOW_RESET=true` only for the coordinated destructive reset;
3. replace placeholders and deploy MCPTools;
4. deploy RCAAgent and RemediatorAgent;
5. deploy AgentOrchestrator;
6. deploy AnomalyDetector;
7. optionally deploy Evaluation independently.

Each component ConfigMap supplies the non-secret `/app/.env` file. Ansible
Vault does not render application credentials. Replace every required
`++++++++` after copying the owning component's
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, keep
populated values uncommitted, and ensure pairwise tokens match. Do not put
passwords, tokens, or database DSNs in ConfigMaps.

Istio base, control plane, ingress gateway, and newly injected workload proxies
are pinned to the tested release in `ansible/group_vars/all.yml`; an empty or
floating Istio version is rejected. Use `playbooks/istio.yml` for an Istio-only
reconciliation so unrelated platform charts are not upgraded.

After rotating the DatabaseJob password, rerun `EvaluationPlatform/Orchestrator/Database/deploy.sh`.
PostgreSQL stores its role password in the persistent data volume, so the
script rolls the StatefulSet and synchronizes that role over its local socket
before migration.
