# real-pod-checkoutservice-cpu-all-one-hour

## RCA

- **Incident pattern:** Checkout requests slow down or fail while browsing and
  other non-checkout operations may continue to work.
- **Affected scope:** All running `checkoutservice` replicas are CPU constrained,
  so the checkout orchestration path has no healthy instance to receive work.
- **Root cause:** An abnormal CPU-intensive execution path or runaway process in
  `checkoutservice` is consuming its available CPU and causing sustained
  service CPU saturation.
- **Corroborating evidence:** High CPU usage or throttling across every
  `checkoutservice` pod, elevated checkout latency or errors, and downstream
  calls waiting behind checkout support a service-wide CPU problem rather than
  ordinary HPA activity or a single dependency failure.

## Recommended remediation

- Prefer vertical scaling when the existing replicas can safely handle the
  workload: increase `checkoutservice` CPU requests and limits using measured
  usage, throttling, and available node capacity as the sizing basis.
- Alternatively, use horizontal scaling with an explicit, capacity-tested HPA
  maximum so `checkoutservice` gains enough replicas to recover without growing
  to an excessive instance count or exhausting cluster capacity.
- Apply either scaling change as a controlled rollout that preserves checkout
  availability, and confirm that dependent payment, shipping, cart, and
  notification calls can complete.
- Verify that CPU usage and throttling fall across `checkoutservice` and that
  checkout latency, errors, traffic, endpoint health, and completed transactions
  recover.
