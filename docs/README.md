# Agent platform documentation

The implemented platform detects Kubernetes anomalies, commits them to a
durable coordinator, performs evidence-backed RCA, requires approval for
mutations, remediates through guarded tools, and evaluates the outcome.

Read in this order:

1. [Architecture](architecture.md)
2. [Runtime flows](flows.md)
3. [Components](components.md)
4. [Data and API contracts](data-contracts.md)
5. [Dependencies](dependencies.md)
6. [Infrastructure](infrastructure.md)
7. [Operations and rollout](operations.md)
8. [Evaluation](evaluation.md)
9. [Detector adaptation API](../AnomalyDetector/docs/agent-api.md)

`KubernetesCloudAgent/` is retained only as a migration reference and is no
longer deployable. Database DDL belongs exclusively to `Orchestrator/` and all
cluster installation belongs to `Infrastructure/`.
