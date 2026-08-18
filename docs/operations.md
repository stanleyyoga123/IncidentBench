# Operations and rollout

## Incompatible rollout

1. Back up anything that must survive. Legacy agent workflow rows are deleted.
2. Scale the old CloudAgent and AnomalyDetector down.
3. Install platform prerequisites with Infrastructure `site.yml`.
4. Copy `DatabaseJob/kubernetes/secret.example.yml` to ignored
   `kubernetes/secret.yml`, replace every `++++++++` placeholder, and run
   `ALLOW_AGENT_WORKFLOW_RESET=true ./DatabaseJob/deploy.sh`. Migration
   `20260817_0002` must finish before any service starts.
5. Copy each component `secret.example.yml` to ignored `secret.yml`, replace
   placeholders while keeping the pairwise token matrix matching, then deploy
   MCPTools, RCAAgent/RemediatorAgent, AgentOrchestrator, and AnomalyDetector
   in that order. `AGENT_STORE_TOKEN` must match across Orchestrator, RCA, and
   Remediator.
6. Verify `/health` for both MCP profiles, both job services, and the
   orchestrator; verify MCP discovery with the appropriate tokens.
7. Confirm committed detector ingestion.
8. Exercise no-action, decline, and approved-remediation mocked flows before a
   controlled live experiment.

Downgrade recreates legacy table structure only. Deleted records are not
recoverable. Return `ALLOW_AGENT_WORKFLOW_RESET` to false after migration.

## Development image rollout

After the platform and database have been installed, the root
`build-push-deploy-dev.sh` delegates build and deployment to the five agent
components in dependency order. Docker Buildx, Docker Hub authentication,
populated component Secrets, and a valid kubectl current context are required:

```bash
./build-push-deploy-dev.sh
```

The script mutates kubectl's current cluster. It accepts no context argument and
does not install platform prerequisites or run DatabaseJob.

## Local verification

Run component tests and Python compilation, parse every YAML document, run
`ansible-playbook --syntax-check`, and inspect OpenAPI operation IDs. These
checks must not apply resources to a live cluster.

Operational symptoms map to boundaries: ingestion errors belong between
detector/orchestrator; queued jobs with a valid slot holder are normal; expired
RCA leases are retried within limits; expired remediation leases become
`needs_review`; MCP 401 errors indicate token/profile mismatch; RBAC denial is
expected when an investigation caller attempts mutation.
