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

## Cluster topology

The bundled inventory and canonical placement profiles assume one control-plane
node, a dedicated tools node with `role=tools`, and six service workers named
`worker-node-1` through `worker-node-6` with `role=services`. Observability and
agent workloads use the tools label; application placement and network probes
use the service label.

The inventory example uses placeholder hostnames, and Runner's
`config/environment.example.json` uses documentation IP addresses. Copy them to
the ignored local inventory and environment files, then supply real SSH addresses,
users, and Kubernetes node InternalIPs. Service DNS names ending in
`.svc.cluster.local` are in-cluster defaults.

To use another topology, update these together:

- Initialization inventory, role labels, and platform node selectors;
- Runner environment `node_ips` keys and values;
- application placement profiles and their node bindings;
- scenario chaos selectors and peer-delay schedules referencing those nodes.

Changing addresses alone does not adapt a scenario targeting a specific node.
Validate every selected scenario before running an experiment.

## Image configuration

Every first-party build and deploy script requires `IMAGE_REGISTRY` and
`IMAGE_TAG`, supplied through the shell (see `deployment/image.env.example`).
The scripts share `deployment/image_config.sh` for naming and validation.
Checked-in workload YAML uses `incidentbench.invalid/<component>:configure-me`
markers; deploy scripts replace them only in the streamed manifest. Upstream
images such as PostgreSQL keep their own references. No public first-party image
registry is assumed. Build/push the chosen version before deploying it.
