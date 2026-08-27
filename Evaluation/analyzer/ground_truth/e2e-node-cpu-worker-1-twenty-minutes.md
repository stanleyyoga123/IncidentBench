# e2e-node-cpu-worker-1-twenty-minutes

## RCA

The injected fault is CPU stress on `worker-node-1`.

## Recommended remediation

Cordon and drain `worker-node-1`, keep it unschedulable while the stress remains,
and verify service recovery. Do not uncordon the faulty node.
