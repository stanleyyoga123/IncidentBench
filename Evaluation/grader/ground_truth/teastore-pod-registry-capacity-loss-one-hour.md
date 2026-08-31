# teastore-pod-registry-capacity-loss-one-hour

## RCA

- **Incident pattern:** Service discovery fails whenever the single `teastore-registry` replica becomes unavailable, and TeaStore paths that depend on registry lookups degrade together.
- **Affected scope:** The only running `teastore-registry` replica is unable to serve traffic; there is no second catalog instance to absorb the loss.
- **Root cause:** `teastore-registry` is an in-memory singleton. A pod failure or local runtime interruption removes the whole catalog until that replica is restored.
- **Corroborating evidence:** Zero ready registry endpoints, failed heartbeats or lookups from other TeaStore services, and no remaining healthy registry pod support a singleton outage rather than an HPA or N+1 capacity miss.

## Recommended remediation

- Restore the existing Deployment replica: wait for the pod to become Ready, or restart/recreate `teastore-registry` in namespace `teastore` if it stays unready.
- Do not add a second registry replica or introduce an HPA. Extra registry instances do not share the in-memory catalog and split registrations.
- If the restored replica is CPU or memory constrained, raise its requests and limits on the Deployment instead of scaling horizontally.
- Verify one Ready registry pod, successful service registrations and heartbeats, and recovered latency, errors, and completed store requests.
