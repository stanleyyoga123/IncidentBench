# Agent platform documentation

The implemented platform detects Kubernetes anomalies, commits them to a
durable coordinator, performs evidence-backed RCA, automatically submits
required remediation with a snapshot hash, remediates through guarded tools,
evaluates the outcome, and turns successful workflows into reusable lessons.

Read in this order:

1. [Architecture](architecture.md)
2. [Runtime flows](flows.md)
3. [Components](components.md)
4. [Data and API contracts](data-contracts.md)
5. [Dependencies](dependencies.md)
6. [Infrastructure](infrastructure.md)
7. [Operations and rollout](operations.md)
8. [Evaluation](evaluation.md)
9. [Detector adaptation API](../Agents/AnomalyDetector/docs/agent-api.md)

Detailed component internals:

- [AgentOrchestrator flow](../EvaluationPlatform/Orchestrator/docs/architecture-and-flow.md)
- [AnomalyDetector flow](../Agents/AnomalyDetector/docs/architecture-and-flow.md)
- [RCAAgent flow](../Agents/RCAAgent/docs/architecture-and-flow.md)
- [RemediatorAgent flow](../Agents/RemediatorAgent/docs/architecture-and-flow.md)
- [LearningAgent flow](../Agents/LearningAgent/docs/architecture-and-flow.md)
- [MCPTools flow](../Agents/MCPTools/docs/architecture-and-flow.md)
- [DatabaseJob schema and migration flow](../EvaluationPlatform/Orchestrator/Database/docs/architecture-and-flow.md)

The legacy KubernetesCloudAgent monolith has been removed. Each component owns
its Kubernetes resources, placeholder Secret, and deployment. DatabaseJob owns
PostgreSQL, local Compose, migrations, and database deployment. Infrastructure
installs only cluster/platform prerequisites and namespaces.
