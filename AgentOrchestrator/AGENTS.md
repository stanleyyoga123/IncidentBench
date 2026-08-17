# AgentOrchestrator instructions

Own anomaly ingestion and durable workflow coordination, not RCA logic or
cluster tools. Preserve separate ingestion/control tokens, deterministic event
idempotency, optimistic workflow versions, the 60-second/100-event claim
defaults, and explicit approval before remediation. Applications may perform
DML only; schema changes belong to `../DatabaseJob/`. Downstream failures must
remain visible and retry must create an explicitly versioned submission.

Own `kubernetes/configmap.yaml` for non-secret runtime configuration and
`kubernetes/manifest.yaml` for the Deployment and ClusterIP Service.
Infrastructure owns credential Secret rendering and ordered installation.

Run `PYTHONPATH=app pytest -q` and `python -m compileall -q app tests`.
