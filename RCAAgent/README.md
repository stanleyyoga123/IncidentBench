# RCAAgent

RCAAgent accepts authenticated asynchronous RCA jobs and uses the investigation
MCPTools service for evidence. Jobs are durable in AgentOrchestrator and
serialized with remediation through the shared execution slot. See `/docs` for
OpenAPI.

RCA session memory stores prior triggering prompts and RCA output as untrusted
historical context. Remediation execution and remediation prompts belong only
to RemediatorAgent.

This component owns its ConfigMap, placeholder Secret,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. `RCA_SUBMIT_TOKEN` must match
AgentOrchestrator, `AGENT_STORE_TOKEN` must match AgentOrchestrator and
RemediatorAgent, and `MCP_TOKEN` must match only the investigation MCP
Secret. Deploy after MCPTools and DatabaseJob.
