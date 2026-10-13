# IncidentBench documentation

IncidentBench runs controlled Kubernetes incident experiments, captures their
evidence, and grades incident-response outputs and application behavior. The
bundled reference agents provide detection, RCA, guarded remediation, and
evidence-linked learning; another response system can use the Runner's lifecycle
integrations.

Start with the [project quickstart](../README.md),
[Runner guide](../EvaluationPlatform/Runner/README.md),
[Grader guide](../EvaluationPlatform/Grader/README.md), and
[reporting guide](../EvaluationPlatform/Grader/reporting/README.md).

For the reference agent platform, read:

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

- [EvaluationOrchestrator persistence](../EvaluationPlatform/Orchestrator/docs/architecture-and-flow.md)
- [AgentOrchestrator flow](../Agents/Orchestrator/docs/architecture-and-flow.md)
- [AnomalyDetector flow](../Agents/AnomalyDetector/docs/architecture-and-flow.md)
- [RCAAgent flow](../Agents/RCAAgent/docs/architecture-and-flow.md)
- [RemediatorAgent flow](../Agents/RemediatorAgent/docs/architecture-and-flow.md)
- [LearningAgent flow](../Agents/LearningAgent/docs/architecture-and-flow.md)
- [MCPTools flow](../Agents/MCPTools/docs/architecture-and-flow.md)
- [DatabaseJob schema and migration flow](../EvaluationPlatform/Database/docs/architecture-and-flow.md)

The legacy KubernetesCloudAgent monolith has been removed. Each component owns
its Kubernetes resources, placeholder Secret, and deployment. DatabaseJob owns
PostgreSQL, local Compose, migrations, and database deployment. Infrastructure
installs only cluster/platform prerequisites and namespaces.
