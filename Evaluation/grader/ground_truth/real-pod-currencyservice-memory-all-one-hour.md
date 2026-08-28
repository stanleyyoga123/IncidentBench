# real-pod-currencyservice-memory-all-one-hour

## RCA

- **Incident pattern:** Price conversion becomes slow or unreliable across
  storefront and checkout flows while unrelated services and node memory remain
  healthy.
- **Affected scope:** Every running `currencyservice` replica approaches its
  container memory limit, leaving no instance with adequate memory headroom.
- **Root cause:** `currencyservice` is vertically under-sized for sustained
  working-set growth, such as a larger conversion cache, request concurrency, or
  runtime heap demand.
- **Corroborating evidence:** High working-set and memory-limit utilization on all
  currency pods, allocation or OOM evidence, currency-specific latency, and
  healthy node memory distinguish this from host-wide pressure.

## Recommended remediation

- Use `kubectl set resources deployment/currencyservice -n online-boutique
  --containers=server` to increase memory requests and limits based on measured
  working set plus safe operating headroom.
- Confirm the new memory request fits eligible-node capacity and preserves all
  required replicas as schedulable.
- Preserve CPU settings unless CPU evidence independently justifies a change;
  do not horizontally scale as a substitute for insufficient per-pod memory.
- Verify the applied resources, stable memory below the new limit, absence of OOM
  events, ready endpoints, restored conversion latency and errors, and successful
  storefront and checkout requests.
