# real-node-loss-worker-3-one-hour

## RCA

The injected fault is network packet loss on `worker-node-3`, causing unreliable
node-to-node communication, retries, errors, and service degradation.

## Recommended remediation

Cordon and drain `worker-node-3`, keep it unschedulable while packet loss remains,
and verify recovery using application errors, latency, traffic, traces, health
checks, or equivalent network evidence. Uncordoning the faulty node is harmful.
