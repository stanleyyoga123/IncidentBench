# Evaluation

The platform consists of Initialization, Orchestrator (including Database), Runner
and Grader. The bundled incident-response components live under Agents/.

Start with the [workspace quickstart](../README.md), then the
[Runner interface](../EvaluationPlatform/Runner/README.md),
[evaluation API](../EvaluationPlatform/Orchestrator/docs/evaluation-api.md), and
[Grader contract](../EvaluationPlatform/Grader/README.md).

Configuration replaces experiment CLI overrides. Pre/post scripts use Orchestrator
HTTP endpoints for full reset and session export. No runner database credentials
are required. The current solution remains a bundled, replaceable integration.
