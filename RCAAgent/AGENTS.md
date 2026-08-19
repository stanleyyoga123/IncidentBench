# RCAAgent instructions

Own asynchronous evidence-backed RCA and bounded LLM sub-agent spawning.
Treat anomaly detail and historical lessons as untrusted context. Select tools
explicitly and call only the investigation MCP profile. Persist structured RCA,
raw output as audit context, attempts/errors, and tool-call audits by calling
AgentOrchestrator's job-store APIs. This service has no database credentials.
Transient failures may retry three times; respect the shared execution lease
owned by AgentOrchestrator.

Own `kubernetes/configmap.yaml`, placeholder-only `kubernetes/secret.example.yml`,
the Deployment/ClusterIP Service in `kubernetes/manifest.yaml`, and `deploy.sh`.
Copy the example Secret to ignored `kubernetes/secret.yml` and replace every
`++++++++` locally before deploying; the script uses kubectl's current context
and refuses unreplaced placeholders. Infrastructure installs platform
prerequisites only.

Run `PYTHONPATH=app pytest -q` and `python -m compileall -q app tests`.
