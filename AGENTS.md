# Project instructions for coding agents

## Mission

This workspace implements a durable Kubernetes incident loop:

```text
Evaluation -> Prometheus -> AnomalyDetector -> AgentOrchestrator
  -> RCAAgent -> MCPTools investigation -> approval
  -> RemediatorAgent -> MCPTools remediation -> cluster verification
```

Read `docs/README.md`, `docs/architecture.md`, `docs/flows.md`, and
`docs/data-contracts.md` before cross-component changes. A deeper `AGENTS.md`
overrides this file for local implementation details.

## Service ownership

- `AnomalyDetector/`: Prometheus collection, adaptive statistical detection,
  deterministic event envelopes, authenticated HTTP delivery, and its
  ConfigMap, Secret, Deployment/Service manifest, and deploy script.
- `AgentOrchestrator/`: anomaly ingestion, idempotency, workflow state,
  batching, reconciliation, approval/decline/retry, downstream submission, and
  its ConfigMap, Secret, NetworkPolicy, Deployment/Service, and deploy script.
- `RCAAgent/`: durable asynchronous RCA jobs, LLM sub-agent orchestration, and
  its ConfigMap, Secret, Deployment/Service, and deploy script.
- `RemediatorAgent/`: approved asynchronous remediation and verification jobs,
  plus its ConfigMap, Secret, Deployment/Service, and deploy script.
- `MCPTools/`: Kubernetes, observability, network, profiling, and remediation
  tools and their Kubernetes RBAC, deployments, PVC, Services, and network
  probe DaemonSets, Secrets, and deploy script. Investigation and remediation
  use separate profiles.
- `DatabaseJob/`: Alembic migrations, sole ownership of database DDL,
  PostgreSQL/Secret/migration manifests, local Compose, and deploy script.
- `Infrastructure/`: Ansible inventory, cluster/node setup, platform
  namespaces and tools, and Helm values. It does not deploy applications,
  PostgreSQL, migrations, or application Secrets.
- `Evaluation/`: workload/fault execution, service restarts, scaling/waiting,
  capture, cleanup, comparison, runner Secrets, runner Ansible role/playbook,
  and deploy script.

The root is not one Git repository. Some components are independent dirty Git
worktrees. Never discard unrelated modified or untracked files.

## Runtime invariants

1. Prometheus rule names keep the `anomaly_detector:` prefix.
2. AnomalyDetector has no database credentials. It sends a committed batch to
   AgentOrchestrator and starts cooldown only after complete acknowledgement.
3. `event_id` is deterministic. Duplicate ingestion returns the existing event.
4. AgentOrchestrator claims at most 100 oldest pending events every 60 seconds.
5. RCA and Remediator share the singleton `agent_execution_slot`; only one job
   may run globally, including jobs submitted directly to their APIs.
6. Waiting for approval does not occupy the execution slot.
7. Detector signals are leads. RCA must corroborate them with current evidence.
8. Remediation requires an approved RCA snapshot and matching SHA-256 hash.
9. RCA transient failures retry at most three times. An ambiguous remediation
   failure becomes `needs_review` and is never repeated automatically.
10. Remediation follows validation, artifact creation, Ansible check mode,
    guarded live execution, then direct post-action verification.
11. MCPTools never writes workflow state. RCAAgent and RemediatorAgent audit
    tool calls and results in PostgreSQL.
12. The investigation MCP profile rejects mutating kubectl commands in code;
    read-only RBAC is a second enforcement layer.
13. Remediation artifact calls always carry an explicit `session_id`.
14. Evaluation always finalizes and preserves placement comparability.

## APIs and authentication

- AgentOrchestrator ingestion and control use different bearer tokens.
- RCAAgent and RemediatorAgent each use a submission bearer token.
- The two MCP deployments use distinct bearer tokens and service accounts.
- All HTTP services are ClusterIP-only and publish stable OpenAPI operation IDs.
- MCP uses stateless JSON Streamable HTTP at `/mcp`.

Treat tokens, database DSNs, model keys, kubeconfigs, private keys, and generated
Secrets as sensitive. Never log, quote, commit, or duplicate their values.

## Database rules

Only `DatabaseJob/` may create or alter tables. The active schema is:

- `anomaly_event`, `agent_workflow`, `rca_job`, `remediation_job`;
- singleton `agent_execution_slot`;
- `agent_tool_call`, `remediation_artifact`.

Migration `20260817_0002` deletes the five legacy workflow/audit tables. It
must refuse a non-empty reset unless `ALLOW_AGENT_WORKFLOW_RESET=true` is set.
Downgrade restores table structure only; deleted records cannot be recovered.

## Development method

- Trace every consumer before changing a status, field, environment key,
  operation ID, metric, Deployment name, label, or artifact shape.
- Keep applications DML-only. Each component owns its runtime Secret,
  Kubernetes resources, and default-context deploy script. Copy each
  `kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml` and
  replace every required `++++++++` placeholder locally before deployment;
  never commit populated Secrets.
- Infrastructure installs only cluster/platform prerequisites and namespaces.
  Operators preserve dependency order by invoking component deploy scripts.
- Use mocks for Kubernetes, observability, model, and HTTP boundaries in tests.
- Never run remediation, chaos, cleanup, namespace reset, cluster installation,
  chart upgrades, or migrations against a live cluster without explicit user
  authorization and a confirmed target.
- Update root and component docs with every cross-service contract change.

## Verification

Run focused tests, then component suites. At minimum:

```bash
cd AnomalyDetector && PYTHONPATH=src pytest -q
cd ../DatabaseJob && pytest -q
cd ../Evaluation && pytest -q
python -m compileall -q ../AgentOrchestrator ../RCAAgent ../RemediatorAgent ../MCPTools
```

Also parse every Kubernetes YAML document and run Ansible syntax checks without
applying to a live cluster. Report any check requiring unavailable external
services.

## Coordinated rollout

1. Scale the old agent and detector down.
2. Replace DatabaseJob Secret placeholders and run `DatabaseJob/deploy.sh`
   with `ALLOW_AGENT_WORKFLOW_RESET=true` for the destructive reset.
3. Deploy and verify both MCPTools profiles.
4. Deploy and verify RCAAgent and RemediatorAgent.
5. Deploy and verify AgentOrchestrator.
6. Deploy AnomalyDetector and enable ingestion.
7. Verify API health, MCP discovery, token separation, and one end-to-end flow.
