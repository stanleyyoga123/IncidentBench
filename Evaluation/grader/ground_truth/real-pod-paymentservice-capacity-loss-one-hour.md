# real-pod-paymentservice-capacity-loss-one-hour

## RCA

- **Incident pattern:** Payment calls become overloaded or intermittently fail
  whenever one `paymentservice` replica is unavailable, while preceding shopping
  operations remain healthy.
- **Affected scope:** One payment replica at a time cannot serve traffic; the
  remaining healthy replica lacks sufficient redundant transaction capacity.
- **Root cause:** `paymentservice` is under-provisioned for routine single-pod
  loss and does not maintain adequate N+1 capacity for the current checkout load.
- **Corroborating evidence:** One missing or unready payment endpoint, saturation
  on the surviving endpoint, healthy CPU before the loss, and payment-stage
  checkout failures support a replica-capacity diagnosis.

## Recommended remediation

- Use `kubectl patch hpa paymentservice-hpa -n online-boutique` to increase
  `minReplicas` enough to retain at least two healthy payment endpoints during a
  single replica loss.
- Set an explicit, capacity-tested `maxReplicas` in the same HPA patch to prevent
  uncontrolled instance growth and excessive cluster resource consumption.
- Size the bounds from transaction load, per-pod capacity, failure tolerance,
  available nodes, and payment idempotency requirements.
- Verify HPA bounds, desired and ready replicas, endpoint count during one
  unavailable pod, balanced transaction traffic, payment latency and errors, and
  successful checkouts without duplicate charges.
