# RemediatorAgent

RemediatorAgent accepts explicitly approved RCA results, queues durable jobs,
and uses the remediation MCPTools profile. A started job is never automatically
retried after failure; ambiguous outcomes become `needs_review`.

The service receives the approved structured RCA snapshot as JSON, persists
tool-created artifacts separately, and returns their filenames in the completed
remediation result.

This component owns its ConfigMap, placeholder Secret,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. `REMEDIATOR_SUBMIT_TOKEN` must match
AgentOrchestrator, while `MCP_TOKEN` must match only the remediation MCP
Secret. Deploy after MCPTools and DatabaseJob.
