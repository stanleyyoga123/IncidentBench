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

## Container image

Set `IMAGE_REGISTRY` and `IMAGE_TAG` before using this component's build or
deploy script. For example, `IMAGE_REGISTRY=ghcr.io/my-org` and
`IMAGE_TAG=v1.0.0` produce an image under that registry and tag. The build
script pushes it; the deploy script renders the same reference into the
first-party Kubernetes manifest before applying it. The checked-in
`incidentbench.invalid/*:configure-me` reference is a non-pullable marker.
Third-party images are unaffected.
