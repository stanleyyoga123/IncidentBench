# Dependencies

| Consumer | Required dependency |
| --- | --- |
| AnomalyDetector | Prometheus; AgentOrchestrator ingestion API |
| AgentOrchestrator | PostgreSQL; RCAAgent, RemediatorAgent, and LearningAgent public job APIs |
| RCAAgent | AgentOrchestrator job-store API; investigation MCP; OpenAI-compatible model; optional Langfuse |
| RemediatorAgent | AgentOrchestrator job-store API; remediation MCP; OpenAI-compatible model; optional Langfuse |
| LearningAgent | AgentOrchestrator job-store API; OpenAI-compatible model; optional Langfuse |
| MCPTools | Kubernetes API; Prometheus; Loki; Jaeger; utility network probes |
| DatabaseJob | Kubernetes API or Docker Compose; PostgreSQL |
| Evaluation | Kubernetes API; Infrastructure inventory/manifests; workload generator |

Python services require FastAPI/Pydantic; AgentOrchestrator and DatabaseJob
use psycopg. MCPTools and MCP clients use the official MCP Python SDK 2.x with
stateless JSON Streamable HTTP. Remediation additionally requires Ansible,
`ansible-runner`, the `kubernetes` Python client, `jsonpatch`, and the
`kubernetes.core` Ansible collection.

Authentication is pairwise: detector ingestion, orchestrator control,
orchestrator job-store, RCA submission, remediation submission, learning submission, investigation
MCP, and remediation MCP all use separate bearer secrets.

Required matches are:

- AnomalyDetector `AGENT_INGESTION_TOKEN` =
  AgentOrchestrator `AGENT_INGESTION_TOKEN`;
- AgentOrchestrator `AGENT_STORE_TOKEN` = RCAAgent `AGENT_STORE_TOKEN` =
  RemediatorAgent `AGENT_STORE_TOKEN`;
- AgentOrchestrator `RCA_SUBMIT_TOKEN` = RCAAgent `RCA_SUBMIT_TOKEN`;
- AgentOrchestrator `REMEDIATOR_SUBMIT_TOKEN` =
  RemediatorAgent `REMEDIATOR_SUBMIT_TOKEN`;
- AgentOrchestrator `LEARNING_SUBMIT_TOKEN` =
  LearningAgent `LEARNING_SUBMIT_TOKEN`;
- AgentOrchestrator `AGENT_STORE_TOKEN` = LearningAgent `AGENT_STORE_TOKEN`;
- RCAAgent `MCP_TOKEN` = investigation MCP `MCP_TOKEN`;
- RemediatorAgent `MCP_TOKEN` = remediation MCP `MCP_TOKEN`.

`AGENT_CONTROL_TOKEN`, detector profile control, model credentials, and the two
MCP bearer values remain independent.
