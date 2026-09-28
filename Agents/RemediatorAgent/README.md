# RemediatorAgent

RemediatorAgent accepts explicitly approved RCA results, queues durable jobs,
and uses the remediation MCPTools profile. A started job is never automatically
retried after failure; a nonempty final output completes as `succeeded`, even when recovery is unverified.

The service receives the approved structured RCA snapshot as JSON, records
tool-created artifacts through AgentOrchestrator, and returns their filenames
in the completed remediation result.

Detailed approval, validation, check/live execution, verification, and failure
flows are indexed in [`docs/README.md`](docs/README.md).

This component owns its ConfigMap, placeholder Secret,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. `REMEDIATOR_SUBMIT_TOKEN` must match
AgentOrchestrator, `AGENT_STORE_TOKEN` must match AgentOrchestrator, RCAAgent,
and LearningAgent, and `MCP_TOKEN` must match only the remediation MCP
Secret. Deploy after MCPTools and DatabaseJob.

### Output persistence

Generated final text is saved through Orchestrator's authenticated job-output
endpoint before parsing. Any nonempty final output completes as `succeeded`;
this means output completion, not successful execution or verified recovery.
Execution errors and recovery observations remain in the output and tool audits.
Empty output or errors preventing durable completion remain `failed`.

## Container image

Set `IMAGE_REGISTRY` and `IMAGE_TAG` before using this component's build or
deploy script. For example, `IMAGE_REGISTRY=ghcr.io/my-org` and
`IMAGE_TAG=v1.0.0` produce an image under that registry and tag. The build
script pushes it; the deploy script renders the same reference into the
first-party Kubernetes manifest before applying it. The checked-in
`incidentbench.invalid/*:configure-me` reference is a non-pullable marker.
Third-party images are unaffected.
