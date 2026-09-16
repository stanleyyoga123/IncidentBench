# LearningAgent

LearningAgent creates durable, reusable incident lessons from successful RCA and
remediation outcomes. It exposes asynchronous authenticated jobs, uses no MCP
tools, and persists only through AgentOrchestrator's internal store API.

See [`docs/README.md`](docs/README.md) for the detailed learning lifecycle and
HTTP contract. Deploy after the DatabaseJob migration and before
AgentOrchestrator.

### Output persistence

Generated final text is saved through Orchestrator's authenticated job-output
endpoint before parsing or verification. Failed jobs retain `raw_output` in
session exports. Remediation jobs with nonempty output complete as `succeeded`;
that status does not prove successful execution or recovery.

Remediation `succeeded` and the `remediated` workflow path indicate completed
agent output, not proven recovery. Learning assesses actual result and tool
evidence, including failed, skipped, or unverified actions.
