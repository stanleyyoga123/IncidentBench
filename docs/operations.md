# Operations and rollout

## Incompatible rollout

1. Back up anything that must survive. Legacy agent workflow rows are deleted.
2. Scale the old CloudAgent and AnomalyDetector down.
3. Set `allow_agent_workflow_reset=true` only for this coordinated deployment.
4. Run the Ansible applications play. Migration `20260817_0002` must finish
   before any service starts.
5. Verify `/health` for both MCP profiles, both job services, and the
   orchestrator; verify MCP discovery with the appropriate tokens.
6. Deploy/scale AnomalyDetector and confirm committed ingestion.
7. Exercise no-action, decline, and approved-remediation mocked flows before a
   controlled live experiment.

Downgrade recreates legacy table structure only. Deleted records are not
recoverable. Return `allow_agent_workflow_reset` to false after migration.

## Local verification

Run component tests and Python compilation, parse every YAML document, run
`ansible-playbook --syntax-check`, and inspect OpenAPI operation IDs. These
checks must not apply resources to a live cluster.

Operational symptoms map to boundaries: ingestion errors belong between
detector/orchestrator; queued jobs with a valid slot holder are normal; expired
RCA leases are retried within limits; expired remediation leases become
`needs_review`; MCP 401 errors indicate token/profile mismatch; RBAC denial is
expected when an investigation caller attempts mutation.
