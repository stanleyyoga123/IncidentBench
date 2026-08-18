# Dependencies

| Consumer | Required dependency |
| --- | --- |
| AnomalyDetector | Prometheus; AgentOrchestrator ingestion API |
| AgentOrchestrator | PostgreSQL; RCAAgent and RemediatorAgent APIs |
| RCAAgent | PostgreSQL; investigation MCP; OpenAI-compatible model; optional Langfuse |
| RemediatorAgent | PostgreSQL; remediation MCP; OpenAI-compatible model; optional Langfuse |
| MCPTools | Kubernetes API; Prometheus; Loki; Jaeger; utility network probes |
| DatabaseJob | Kubernetes API or Docker Compose; PostgreSQL |
| Evaluation | Kubernetes API; Infrastructure inventory/manifests; workload generator |

Python services require FastAPI/Pydantic/psycopg where applicable. MCPTools and
MCP clients use the official MCP Python SDK 2.x with stateless JSON Streamable
HTTP. Remediation additionally requires Ansible and `ansible-runner`.

Authentication is pairwise: detector ingestion, orchestrator control, RCA
submission, remediation submission, investigation MCP, and remediation MCP all
use separate bearer secrets.

Required matches are:

- AnomalyDetector `AGENT_INGESTION_TOKEN` =
  AgentOrchestrator `AGENT_INGESTION_TOKEN`;
- AgentOrchestrator `RCA_SUBMIT_TOKEN` = RCAAgent `RCA_SUBMIT_TOKEN`;
- AgentOrchestrator `REMEDIATOR_SUBMIT_TOKEN` =
  RemediatorAgent `REMEDIATOR_SUBMIT_TOKEN`;
- RCAAgent `MCP_TOKEN` = investigation MCP `MCP_TOKEN`;
- RemediatorAgent `MCP_TOKEN` = remediation MCP `MCP_TOKEN`.

`AGENT_CONTROL_TOKEN`, detector profile control, model credentials, and the two
MCP bearer values remain independent.
