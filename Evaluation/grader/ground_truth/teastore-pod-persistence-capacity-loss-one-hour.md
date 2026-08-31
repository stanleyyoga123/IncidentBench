# teastore-pod-persistence-capacity-loss-one-hour

## RCA

- **Incident pattern:** Latency and errors rise whenever one `teastore-persistence` replica becomes unavailable, while unrelated TeaStore paths remain comparatively healthy.
- **Affected scope:** One replica at a time is unable to serve traffic; the remaining replica is healthy but does not provide enough redundant capacity under the current load.
- **Root cause:** `teastore-persistence` is under-provisioned for a routine single-pod loss, leaving insufficient N+1 capacity when a pod or its local runtime becomes temporarily unavailable.
- **Corroborating evidence:** One missing or unready endpoint, healthy surviving replicas, traffic concentrated on the remaining endpoint, and service-specific saturation or latency support a replica-capacity problem.

## Recommended remediation

- Increase guaranteed capacity with `kubectl patch hpa teastore-persistence-hpa -n teastore`, raising `minReplicas` enough to keep at least two healthy endpoints during one replica loss.
- Set an explicit, capacity-tested `maxReplicas` in the same HPA change so the response cannot create an excessive number of application instances.
- Base the new minimum and maximum on observed request load, per-pod capacity, disruption tolerance, and available cluster resources.
- Verify the HPA bounds, desired and ready replicas, endpoint count during one unavailable pod, latency, errors, traffic distribution, and completed requests.
