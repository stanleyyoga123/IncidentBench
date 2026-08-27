# real-pod-cartservice-cpu-all-one-hour

## RCA

The injected fault is artificial CPU stress affecting the `cartservice` pods.
Sustained service CPU saturation caused by that stressor is the root cause.

## Recommended remediation

Remove or stop the CPU stressor on `cartservice`. If the stressor cannot be
removed immediately, safely add unaffected capacity or move the workload, then
verify that service CPU and application latency, traffic, errors, or health recover.
