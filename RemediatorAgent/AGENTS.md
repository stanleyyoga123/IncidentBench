# RemediatorAgent instructions

Accept only an approved RCA result whose canonical SHA-256 matches the request.
Preserve the sequence: direct read validation, artifact creation, Ansible check
mode, guarded live execution, and direct post-action verification. Any crash or
ambiguous failure after execution starts becomes `needs_review`; never retry a
mutation blindly. Use only the remediation MCP profile and explicit session IDs.

Run `PYTHONPATH=app pytest -q` and `python -m compileall -q app tests`.
