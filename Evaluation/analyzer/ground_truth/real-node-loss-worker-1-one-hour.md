# real-node-loss-worker-1-one-hour

## RCA

The injected fault is network packet loss on `worker-node-1`, causing unreliable
node-to-node communication, retries, errors, and service degradation.

## Recommended remediation

Cordon and drain `worker-node-1`, keep it unschedulable while packet loss remains,
and verify recovery using application errors, latency, traffic, traces, health
checks, or equivalent network evidence. Uncordoning the faulty node is harmful.
