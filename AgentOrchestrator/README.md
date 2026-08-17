# AgentOrchestrator

AgentOrchestrator accepts authenticated AnomalyDetector events, persists them,
and coordinates asynchronous RCA and explicitly approved remediation jobs.
It polls pending events every 60 seconds and batches at most 100 into one
workflow. Only one RCA or remediation execution may hold the shared database
execution slot at a time.

Run Orchestrator migrations before starting. Copy `.env.example` to `.env`,
then run `./run.sh`. OpenAPI is available at `/docs`.
