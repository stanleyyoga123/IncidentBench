# Operations and rollout

## Incompatible rollout

1. Back up anything that must survive. Legacy agent workflow rows are deleted.
2. Scale the old CloudAgent and AnomalyDetector down.
3. Install platform prerequisites with Infrastructure `site.yml`.
4. Copy `EvaluationPlatform/Orchestrator/Database/kubernetes/secret.example.yml` to ignored
   `kubernetes/secret.yml`, replace every `++++++++` placeholder, and run
   `ALLOW_AGENT_WORKFLOW_RESET=true ./EvaluationPlatform/Orchestrator/Database/deploy.sh`. Migration
   Alembic head `20260831_0004` must finish before any service starts.
5. Copy each component `secret.example.yml` to ignored `secret.yml`, replace
   placeholders while keeping the pairwise token matrix matching, then deploy
   MCPTools, LearningAgent, Agents/RCAAgent/RemediatorAgent, AgentOrchestrator, and
   AnomalyDetector in that order. `AGENT_STORE_TOKEN` must match across
   Orchestrator and all three job services.
6. Verify `/health` for both MCP profiles, all three job services, and the
   orchestrator; verify MCP discovery with the appropriate tokens.
7. Confirm committed detector ingestion.
8. Exercise no-action, decline, and approved-remediation mocked flows before a
   controlled live experiment.

For every supported application, keep `collector.metadata.namespaces` in
AnomalyDetector and `workloads.namespaces` in RCAAgent aligned. MCPTools
`APPLICATION_NAMESPACES` binds namespaces that already exist during its
deployment; any installer that deletes and recreates an application namespace
must then reapply `Agents/MCPTools/kubernetes/application-role-binding.yaml` and verify
the remediation service account's intended namespaced permission. Evaluation's
application installer performs both steps automatically.
MCPTools does not create or catalog application namespaces. Evaluation creates
the selected namespace, applies the binding, and verifies both Deployment and
HorizontalPodAutoscaler patch authorization before application installation.
For an application already running outside Evaluation, pass its namespace
explicitly through `APPLICATION_NAMESPACES` when deploying MCPTools.
During upgrade, MCPTools deletes only the obsolete namespaced RoleBinding named
`mcp-tools-remediation` and creates `mcp-tools-remediation-workload`. This name
change avoids Kubernetes' immutable-`roleRef` rejection when migrating from the
old namespaced Role to the workload ClusterRole.

Downgrade recreates legacy table structure only. Deleted records are not
recoverable. Return `ALLOW_AGENT_WORKFLOW_RESET` to false after migration.

## Agent manifest rollout

The root `deploy.sh` invokes the six component deployment scripts in dependency
order, including Orchestrator and both MCP profiles. It checks all component
Secrets before applying resources, uses the current kubectl context, and stops
on the first error. Each agent Deployment is restarted and awaited so mounted
ConfigMaps and Secret environment changes are loaded, including namespace
monitoring changes. Use it when evaluations and agent jobs are idle.

Load the image settings used to build and push this version first:

```bash
source deployment/image.env
./deploy.sh
```

The required `IMAGE_REGISTRY` and `IMAGE_TAG` select the same first-party images
for build and deployment. Copy `deployment/image.env.example` to ignored
`deployment/image.env` and customize it. Workload manifests contain image markers;
component deploy scripts replace only these markers in memory. Apply them through
the scripts, not directly through `kubectl apply -f`.
Build/push images
with the individual component `build.sh` scripts beforehand when required.
Platform initialization, database migrations, application/Runner deployment,
and automatic rollback are outside this command's scope. If a component fails,
previous components may already be updated; fix the cause and rerun.

## Local verification

Run component tests and Python compilation, parse every YAML document, run
`ansible-playbook --syntax-check`, and inspect OpenAPI operation IDs. These
checks must not apply resources to a live cluster.

Operational symptoms map to boundaries: ingestion errors belong between
detector/orchestrator; queued jobs with a valid slot holder are normal; expired
RCA leases are retried within limits; expired remediation leases become
`failed`; MCP 401 errors indicate token/profile mismatch; RBAC denial is
expected when an investigation caller attempts mutation.
Learning jobs share the global slot, retry three times, and then allow the
workflow to complete with `learning_status=failed` and no published lessons.
