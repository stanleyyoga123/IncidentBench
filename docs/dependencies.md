# Dependencies

| Consumer | Required dependency |
| --- | --- |
| AnomalyDetector | Prometheus; AgentOrchestrator ingestion API |
| AgentOrchestrator | PostgreSQL; RCAAgent and RemediatorAgent APIs |
| RCAAgent | PostgreSQL; investigation MCP; OpenAI-compatible model; optional Langfuse |
| RemediatorAgent | PostgreSQL; remediation MCP; OpenAI-compatible model; optional Langfuse |
| MCPTools | Kubernetes API; Prometheus; Loki; Jaeger; utility network probes |
| Evaluation | Kubernetes API; Infrastructure inventory/manifests; workload generator |

Python services require FastAPI/Pydantic/psycopg where applicable. MCPTools and
MCP clients use the official MCP Python SDK 2.x with stateless JSON Streamable
HTTP. Remediation additionally requires Ansible and `ansible-runner`.

Authentication is pairwise: detector ingestion, orchestrator control, RCA
submission, remediation submission, investigation MCP, and remediation MCP all
use separate bearer secrets.
