# Known risks and roadmap

## Immediate security work

Historical and local working files have contained plaintext credentials,
long-lived tokens, database passwords, object-store credentials, and
observability keys. Treat exposed values as compromised even if the cluster is
private.

Priority actions:

1. Revoke and rotate every committed credential.
2. Remove literal values from manifests, command notes, examples, and Git
   history as appropriate for the repository's sharing model.
3. Use Kubernetes Secrets or an external secret manager; commit only placeholder
   manifests or documented secret names.
4. Add secret scanning in local hooks and CI.
5. Review broad cluster-admin bindings and restrict them to the minimum needed
   by the isolated evaluation environment.

The most important locations to audit are component-local populated
`kubernetes/secret.yml` files, ignored local `.env` files,
`Infrastructure/backups/`, and generated kubeconfigs. Committed
`kubernetes/secret.example.yml` files must retain only `++++++++`
placeholders. This document intentionally does not repeat any secret value.

## Current technical inconsistencies

- Infrastructure is now Ansible-managed, but chart versions left empty in
  `group_vars/all.yml` resolve at install time. Pin all versions for repeatable
  research runs.
- Historical Langfuse backup data has been removed from the workspace; any
  future backups must use managed backup storage.
- Development image tags and external endpoint assumptions remain embedded in
  component manifests; publish and pin immutable release digests.
- Component deploy scripts intentionally use kubectl's current context.
  Operators must verify that context before every mutating rollout.
- The Jaeger store is ephemeral and has a short retention window.
- Component-local agent notes may describe older detector architecture; live
  code and these cross-project docs take precedence for e2e contracts.

## Recommended consolidation sequence

### 1. Secure and establish ownership

- Rotate credentials and remove plaintext secrets.
- Decide whether the workspace becomes a monorepo or remains a coordinated
  multi-repo project.
- Assign an owner and compatibility policy for each cross-component contract.

### 2. Evolve the versioned workflow schema

The Alembic baseline and migration-first deployment contract are now
implemented. Next, add migration integration tests against PostgreSQL, publish
an immutable migration image, and evolve the queue contract additively.

Suggested schema evolution includes an `anomaly_event` table with explicit
status, lease owner/expiry, attempt count, last error, timestamps, and immutable
detector payload, plus separate investigation, remediation, and action-audit
tables. Preserve current IDs or provide a tested migration mapping.

### 3. Harden infrastructure reproducibility

- Pin every chart and application digest in release-specific Ansible vars.
- Add Molecule or disposable-cluster coverage for the Ansible roles.
- Keep database and object-store backups in managed storage outside the workspace.
- Add schema/rule/manifest validation to CI.

### 4. Strengthen runtime delivery

- Claim bounded batches using row locking (`FOR UPDATE SKIP LOCKED`) or a
  lease-based queue contract.
- Add retries, error classification, dead-letter handling, and correlation IDs.
- Add health/readiness endpoints or process checks that test dependencies.
- Define exactly-once audit semantics around remediation actions.

### 5. Strengthen evaluation

- Version scenario and metric contracts.
- Record application, agent, model, prompt, and infrastructure image digests.
- Add explicit success metrics and confidence intervals across repeated runs.
- Automate artifact integrity and invalid-run checks before comparison.

## Decision record needed

Before extending DatabaseJob beyond its migration-only responsibility, decide
whether it should become:

- only a migration/schema package;
- a workflow API/service replacing direct database coupling; or
- an experiment/control-plane service.

These choices have materially different availability, security, and ownership
implications. Do not build all three implicitly in one service.
