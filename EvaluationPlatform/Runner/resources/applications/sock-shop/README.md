# Sock Shop

This application profile bundles the archived upstream Weaveworks
[`microservices-demo`](https://github.com/microservices-demo/microservices-demo)
Sock Shop Kubernetes manifest and adapts it to the Evaluation placement contract.

The canonical overlay keeps the seven stateful or coordination Deployments at one
replica, starts stateless APIs at two replicas, and starts `front-end` at six.
The `catalogue`, `orders`, `payment`, and `shipping` services have rate-limited
CPU HPAs with a maximum of 30 replicas. The `front-end` HPA maintains 6–30
replicas, targets 70% CPU utilization of the application container, and excludes
Istio proxy CPU from its scaling metric. Every container
has CPU and memory requests and limits; the database containers use bounded
ephemeral volumes because the evaluator recreates the namespace for every run.

`canonical-six-node/load-resources/` sizes the affected services from a
100–110-user Locust baseline (about 319 requests/sec). CPU requests/limits are
400m/800m for carts and front-end, 250m/750m for orders and carts-db,
300m/600m for user, 150m/500m for user-db, and 100m/300m for session-db.
Carts, orders, shipping, and queue-master request 512Mi memory with 768Mi
limits. These settings provide headroom over the observed steady load; they
do not guarantee utilization below 100% during startup or injected faults.
Carts, orders, and shipping use HTTP startup/readiness probes and zero-unavailable
rolling updates. Stateful pod replacement still discards their ephemeral data.
The CPU-constrained overlay explicitly resets both requests and limits to 100m
for its three fault targets, preserving the intentional constrained scenarios.

The current deployment-utilization recording rules include native Istio sidecar
usage but omit its init-container requests from the denominator. Consequently
their percentages overstate utilization relative to the complete pod reservation;
resource sizing also considers the individual application-container usage.

The application journey is `resources/applications/sock_shop.py`. It follows the upstream
load test through catalogue discovery, product detail, and an isolated cookie
cart while treating unexpected HTTP responses or unusable catalogue data as
Locust failures. Shared-account checkout is intentionally excluded because
concurrent users race on the same upstream cart and generate false baseline
failures; pod readiness still verifies the order, payment, and user services.

`sock-shop-pod-catalogue-cpu-all-ten-minutes` is exactly ten minutes of scenario
time: five minutes of recurring CPU-only catalogue contention followed by five
minutes of recovery. Application installation, startup warm-up, and a baseline
of at least six minutes precede that ten-minute window; six minutes guarantees
the admission gate receives a full 300-second span of Locust CSV samples.
