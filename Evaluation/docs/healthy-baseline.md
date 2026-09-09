# Establishing a healthy TeaStore baseline

TeaStore needs successful application journeys before fault experiments are
admitted. Pod readiness alone is insufficient. The `result-5` archives contain
baseline HTTP failures and web UI `Request header is too large` logs.

## Workload correction

The old client sent `adress1` / `adress2`. TeaStore's `CartActionServlet`
requires `address1` / `address2` and redirects incomplete orders back to the
order page. HTTP 200 after a redirect therefore did not prove a purchase.
Sessions also accumulated cart contents indefinitely without logout.

The client now runs bounded shopping sessions: login, one to three category and
product browsing actions, one cart addition, checkout, profile, and logout.
It validates the application's confirmation text for login, cart addition,
checkout, and logout. Failures remain recorded by Locust. A failed session ends
and clears its client cookies before a new session starts, preventing indefinite
cookie growth. Cookies are not logged. Think time remains between browsing and
cart actions. This changes the request mix, so old and new results must not be
pooled as identical workloads.

Reference implementation checked during this change:

- [CartActionServlet](https://github.com/DescartesResearch/TeaStore/blob/master/services/tools.descartes.teastore.webui/src/main/java/tools/descartes/teastore/webui/servlet/CartActionServlet.java)
- [AbstractUIServlet](https://github.com/DescartesResearch/TeaStore/blob/master/services/tools.descartes.teastore.webui/src/main/java/tools/descartes/teastore/webui/servlet/AbstractUIServlet.java)

These references describe upstream source, not proof of the exact image running
in a cluster. Validate confirmations against the deployed image during calibration.

## Admission gate

At the end of the TeaStore baseline, before agent startup and chaos:

- Locust must still be running.
- Aggregate CSV counters must be valid, monotonic, and no more than 15 seconds old.
- At least 300 seconds of history must exist, with at least 100 requests in
  the final five-minute window.
- Both the whole-baseline and final-window failure ratios must be at most 1%.
  Semantic failures count alongside HTTP failures; 4xx are not exempted.

Use a baseline of at least ten minutes to allow ramp-up and CSV sampling. These
are initial admission thresholds, not a calibrated latency SLO. The result is
written to `metadata.baseline_health`. Rejection fails the baseline phase and
normal finalization still runs. Online Boutique's admission behavior is unchanged.
Short TeaStore smoke runs must also provide a sufficiently long baseline.

## First calibration on an existing deployment

Start with ten constant users and no agents changing the application. On the
evaluation runner, with the selected endpoint reachable, run:

```bash
python -m locust -f applications/teastore.py --headless \
  --host http://teastore-webui.teastore.svc.cluster.local:8080/tools.descartes.teastore.webui \
  --users 10 --spawn-rate 2 --run-time 10m \
  --csv /tmp/teastore-baseline-10 --html /tmp/teastore-baseline-10.html
```

Use a new output prefix per attempt. This sends application traffic and test
orders; it does not install/reset the application or inject chaos. It does not
run the experiment admission gate. Inspect its request and failure CSVs and
semantic checks. Increase to 25 and then 50 users only after the smaller load
succeeds. Record error rate, P95 latency, completed purchases, CPU throttling,
memory, restarts, Ready endpoints, and replica counts. Do not choose a production
benchmark load until these measurements stabilize.

Any remaining 404 needs the actual failing route and application-side error
context; do not treat it as an expected chaos error. For authentication or
catalog failures, check that database generation has completed and the expected
`user1`–`user99`, category 2–6, and product 7–506 fixtures exist. Do not reset
the database simply to make those assumptions true without confirming the target.

## Full archived baseline run

After confirming the cluster target and authorizing the normal evaluation reset,
use the dedicated idle scenario:

```bash
CONST_USERS=10 CONST_BIAS_USERS=0 CONST_SPAWN_RATE=2 \
  ./run.sh --loadgenerator constant \
  --scenario collections/baseline/01-teastore.json \
  --baseline-minutes 10 --skip-agents
```

The normal `run.sh` prerun resets workflow tables and recreates application
namespaces. Its finalizer also cleans chaos state. The scenario itself injects
no fault. This path records the health gate and snapshots; standalone Locust
above is appropriate when a reset has not been authorized.

## Scheduling and remaining validation

The archived canonical TeaStore pods request about 14.2 CPU cores and 22.5 GiB
including native Istio sidecars. Worker capacities differ, and five archived
runs could not schedule the third 1.6-core web UI pod. Lower traffic does not
reduce CPU requests. Before calibration all desired pods must fit and become
Ready; budget platform reservations and per-node fit. Measure before lowering
requests or increasing replica limits. Resource sizing and live health are not
established by the client unit tests.

Keep the initial baseline at the existing canonical resources; if it fails to
schedule, resolve cluster capacity before running workload calibration. Archive
actual placement and image digests with each accepted run. Do not grade a
rejected baseline as an agent RCA/remediation failure.
