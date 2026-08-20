# RemediatorAgent

RemediatorAgent accepts explicitly approved RCA results, queues durable jobs,
and uses the remediation MCPTools profile. A started job is never automatically
retried after failure; ambiguous outcomes become `needs_review`.

The service receives the approved structured RCA snapshot as JSON, records
tool-created artifacts through AgentOrchestrator, and returns their filenames
in the completed remediation result.

Detailed approval, validation, check/live execution, verification, and failure
flows are indexed in [`docs/README.md`](docs/README.md).

This component owns its ConfigMap, placeholder Secret,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. `REMEDIATOR_SUBMIT_TOKEN` must match
AgentOrchestrator, `AGENT_STORE_TOKEN` must match AgentOrchestrator, RCAAgent,
and LearningAgent, and `MCP_TOKEN` must match only the remediation MCP
Secret. Deploy after MCPTools and DatabaseJob.
