# RCAAgent

RCAAgent accepts authenticated asynchronous RCA jobs and uses the investigation
MCPTools service for evidence. Jobs are durable in PostgreSQL and serialized
with remediation through the shared execution slot. See `/docs` for OpenAPI.
