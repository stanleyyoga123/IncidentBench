# MCPTools

MCPTools serves the former monolithic agent tools over authenticated MCP
Streamable HTTP at `/mcp`. The same image runs as `investigation` and
`remediation` profiles with distinct bearer tokens, allowlists, and Kubernetes
service accounts. The remediation profile stores session files on its mounted
PVC and never writes workflow data directly to PostgreSQL.

`kubernetes/` owns both profile Deployments and Services, their RBAC, the
remediation PVC, and the overlay/underlay probe DaemonSets. Infrastructure
renders runtime Secrets and installs these resources before the job services.
