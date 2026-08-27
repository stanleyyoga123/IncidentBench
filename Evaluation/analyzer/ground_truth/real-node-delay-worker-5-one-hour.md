# real-node-delay-worker-5-one-hour

## RCA

The injected fault is severe network delay on `worker-node-5` and on peer paths
to that node. It produces high inter-node RTT and downstream service latency;
ordinary CPU, HPA, or replica behavior is not the root cause.

## Recommended remediation

Cordon and drain `worker-node-5` so affected workloads move to healthy nodes,
then verify recovery with application latency, traffic, error, trace, or health
evidence. Keep the node unschedulable until its network fault is removed; do not
uncordon it merely because Kubernetes objects and pods are Ready.
