# RCAAgent

RCAAgent accepts authenticated asynchronous RCA jobs and uses the investigation
MCPTools service for evidence. Jobs are durable in AgentOrchestrator and
serialized with remediation and learning through the shared execution slot.
See `/docs` for OpenAPI.

Detailed service behavior is documented in
[`docs/README.md`](docs/README.md), including prompt construction, baseline
profiling, sub-agents, MCP audits, and retry semantics.

Validated historical lessons are supplied by AgentOrchestrator as untrusted
user-prompt context. Remediation execution and prompts belong only to
RemediatorAgent.

This component owns its ConfigMap, placeholder Secret,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. `RCA_SUBMIT_TOKEN` must match
AgentOrchestrator, `AGENT_STORE_TOKEN` must match AgentOrchestrator,
RemediatorAgent, and LearningAgent, and `MCP_TOKEN` must match only the investigation MCP
Secret. Deploy after MCPTools and DatabaseJob.

### Output persistence

Generated final text is saved through Orchestrator's authenticated job-output
endpoint before parsing or verification. Failed jobs retain `raw_output` in
session exports; Remediator also retains its parsed `result` when recovery
verification fails. Failure status remains separate from generated claims.

## Container image

Set `IMAGE_REGISTRY` and `IMAGE_TAG` before using this component's build or
deploy script. For example, `IMAGE_REGISTRY=ghcr.io/my-org` and
`IMAGE_TAG=v1.0.0` produce an image under that registry and tag. The build
script pushes it; the deploy script renders the same reference into the
first-party Kubernetes manifest before applying it. The checked-in
`incidentbench.invalid/*:configure-me` reference is a non-pullable marker.
Third-party images are unaffected.
