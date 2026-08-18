# AgentOrchestrator

AgentOrchestrator accepts authenticated AnomalyDetector events, persists them,
and coordinates asynchronous RCA and explicitly approved remediation jobs.
It polls pending events every 60 seconds and batches at most 100 into one
workflow. Only one RCA or remediation execution may hold the shared database
execution slot at a time.

Run DatabaseJob migrations before starting. Copy `.env.example` to `.env`,
then run `./run.sh`. OpenAPI is available at `/docs`.

This component owns its ConfigMap, placeholder Secret, NetworkPolicy,
Deployment/ClusterIP Service, and `deploy.sh`. Copy
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, replace
every `++++++++`, then run `./deploy.sh` against kubectl's current context.
The script refuses placeholders. Match `AGENT_INGESTION_TOKEN` with
AnomalyDetector, `RCA_SUBMIT_TOKEN` with RCAAgent, and
`REMEDIATOR_SUBMIT_TOKEN` with RemediatorAgent; keep `AGENT_CONTROL_TOKEN`
independent. Deploy after both MCP profiles and the two job services.
