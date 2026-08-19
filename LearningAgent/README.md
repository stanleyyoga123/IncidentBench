# LearningAgent

LearningAgent creates durable, reusable incident lessons from successful RCA and
remediation outcomes. It exposes asynchronous authenticated jobs, uses no MCP
tools, and persists only through AgentOrchestrator's internal store API.

See `docs/agent-api.md` for the HTTP contract. Deploy after the DatabaseJob
migration and before AgentOrchestrator.
