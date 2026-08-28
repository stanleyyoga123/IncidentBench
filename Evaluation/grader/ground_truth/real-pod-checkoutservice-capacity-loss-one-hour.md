# real-pod-checkoutservice-capacity-loss-one-hour

## RCA

- **Incident pattern:** Checkout latency and errors rise whenever one
  `checkoutservice` replica becomes unavailable, while browsing and cart paths
  remain comparatively healthy.
- **Affected scope:** One replica at a time is unable to serve traffic; the
  remaining replica is healthy but does not provide enough redundant checkout
  capacity under the current load.
- **Root cause:** `checkoutservice` is under-provisioned for a routine single-pod
  loss, leaving insufficient N+1 capacity when a pod or its local runtime becomes
  temporarily unavailable.
- **Corroborating evidence:** One missing or unready checkout endpoint, healthy
  surviving replicas, traffic concentrated on the remaining endpoint, and
  checkout-specific saturation or latency support a replica-capacity problem.

## Recommended remediation

- Increase guaranteed checkout capacity with `kubectl patch hpa
  checkoutservice-hpa -n online-boutique`, raising `minReplicas` enough to keep
  at least two healthy endpoints during one replica loss.
- Set an explicit, capacity-tested `maxReplicas` in the same HPA change so the
  response cannot create an excessive number of application instances.
- Base the new minimum and maximum on observed request load, per-pod capacity,
  disruption tolerance, and available cluster resources.
- Verify the HPA bounds, desired and ready replicas, endpoint count during one
  unavailable pod, checkout latency, errors, traffic distribution, and completed
  transactions.
