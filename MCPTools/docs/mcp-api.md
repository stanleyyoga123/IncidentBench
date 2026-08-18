# MCPTools MCP contract

Connect with MCP SDK 2.x JSON Streamable HTTP at `/mcp` and the deployment's
bearer token. The investigation deployment exposes `kubectl`, `prometheus`,
`loki`, Jaeger operations, network operations, and
`cluster.profile_baseline`. Its kubectl wrapper accepts only read operations.

The remediation deployment exposes the same investigation tools plus:

- `remediator.write_file(session_id, filename, content)`
- `remediator.run_ansible(session_id, playbook_file, inventory_file, check, extra_vars)`

Run Ansible with `check=true` first. Live execution is rejected unless the
same session has a successful check record for the exact playbook SHA-256.
Never reuse a session ID across remediation jobs. Tool results are returned to
the calling agent; MCPTools does not persist workflow/audit rows itself.
RCAAgent and RemediatorAgent record those audits through AgentOrchestrator.
