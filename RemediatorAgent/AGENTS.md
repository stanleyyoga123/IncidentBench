# RemediatorAgent instructions

Accept only an approved RCA result whose canonical SHA-256 matches the request.
Preserve the sequence: direct read validation, artifact creation, Ansible check
mode, guarded live execution, and direct post-action verification. Any crash or
ambiguous failure after execution starts becomes `needs_review`; never retry a
mutation blindly. Use only the remediation MCP profile and explicit session IDs.
Persist jobs, leases, tool-call audits, and artifacts by calling
AgentOrchestrator's job-store APIs. This service has no database credentials.

Own `kubernetes/configmap.yaml`, placeholder-only `kubernetes/secret.example.yml`,
the Deployment/ClusterIP Service in `kubernetes/manifest.yaml`, and `deploy.sh`.
Copy the example Secret to ignored `kubernetes/secret.yml` and replace every
`++++++++` locally before deploying; the script uses kubectl's current context
and refuses unreplaced placeholders. Infrastructure installs platform
prerequisites only.

Run `PYTHONPATH=app pytest -q` and `python -m compileall -q app tests`.
