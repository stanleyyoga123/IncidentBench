# Operations and rollout

## Orchestrator split cutover

This split preserves the existing schema, data, submission/result contracts and
archives. It needs no experiment rerun, database migration or reset. In particular,
do not run `Database/deploy.sh`, set `ALLOW_AGENT_WORKFLOW_RESET=true`, or start a
Runner experiment merely to install this change.

1. Arrange a coordinated cutover when no evaluation or agent job is active.
   Stop the old combined orchestrator and detector before replacing services.
2. Populate the two component Secrets locally from their examples. Keep the
   existing database and matching store/ingestion/submission token values.
3. Deploy `EvaluationPlatform/Orchestrator` as `evaluation-orchestrator` against
   the existing database. It serves persistence, lessons and evaluation APIs.
4. Update/restart RCAAgent, RemediatorAgent and LearningAgent with their store
   URL pointing to `http://evaluation-orchestrator.agents.svc.cluster.local:8080`.
5. Deploy `Agents/Orchestrator` as `agent-orchestrator`. Its persistence HTTP
   client points to EvaluationOrchestrator, and its read-only maintenance DSN
   points to the same database. Restore detector ingestion only after health
   checks pass. There must be only one lifecycle coordinator running.
6. Update Runner's ignored environment file `orchestrator_url` to
   `http://evaluation-orchestrator.agents.svc.cluster.local:8080`. Preserve the
   existing control-token reference and all experiment settings.
7. Inspect service health and existing persisted records using authenticated
   reads. Existing archives remain available to the unchanged offline Grader.
   A new live experiment is not an installation check.

Both orchestrators remain online during baseline; the existing advisory lock
serializes evaluation maintenance with dispatch and persistence mutations.
Fresh installations still require DatabaseJob's normal migrations before services
start. Older destructive migrations retain their existing safeguards; they are
not part of this service split.

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

## Agent manifest rollout

The root `deploy.sh` invokes the seven component deployment scripts in dependency
order, including both orchestrators and both MCP profiles. It checks all component
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
