# Sock Shop

This application profile bundles the archived upstream Weaveworks
[`microservices-demo`](https://github.com/microservices-demo/microservices-demo)
Sock Shop Kubernetes manifest and adapts it to the Evaluation placement contract.

The canonical overlay keeps the seven stateful or coordination Deployments at one
replica, starts stateless APIs at two replicas, and starts `front-end` at six.
Only the fault-targeted `catalogue` service receives a rate-limited CPU HPA
(maximum 6); other replicas stay fixed so JVM cold-start CPU cannot amplify
resource use before baseline. Every container
has CPU and memory requests and limits; the database containers use bounded
ephemeral volumes because the evaluator recreates the namespace for every run.

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
