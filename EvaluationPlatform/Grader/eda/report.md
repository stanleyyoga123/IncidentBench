# Experiment metrics report

Generated 2026-09-18T04:08:10.868620+00:00.

## Definitions and configuration

- Rolling window: **5 minutes**; initial baseline exclusion: **5 minutes**.
- Successful output: score **> 0.8**.
- Holistic tolerance: P95 increase **< 20%**, with 5xx **≤ 0.5 requests/s**.
- Repeat selection: `latest_completed_else_latest`. Latest completed attempt per scenario is the default; otherwise the latest attempt.
- Only outputs completed within recorded chaos intervals contribute to scores, counts and timing. Missing boundaries/timestamps are excluded.
- Time to first good output means earliest completion among the highest-scoring outputs, measured from recorded chaos start.
- Differences are window minus baseline; negative means a decrease. Percentage changes are unknown for zero baselines.
- Best minimizes P95 among windows satisfying the 5xx ceiling; worst maximizes P95 without that ceiling. P95 and 5xx share the selected window.
- P95 is a time average of archived rolling percentiles. Missing 5xx samples may be imputed at recorded traffic timestamps; counts are disclosed.
- Holistic totals include completed, evaluable runs only. Unknown values are never zero or success. Session and scenario totals have separate denominators.
- This script reads existing grades and recomputes performance offline. Missing grades leave semantic scores unknown; no model calls occur.
- Archives are discovered recursively, including preserved local campaigns. The attempts table records which runs were selected.

## Aggregate metrics across all applications

| metric | count | evaluable | percent_of_evaluable |
| --- | --- | --- | --- |
| Successful RCA sessions (score &gt; 0.8) | 57 | 229 | 24.8908 |
| Scenarios/runs with successful RCA | 25 | 30 | 83.3333 |
| Successful REMEDIATION sessions (score &gt; 0.8) | 22 | 135 | 16.2963 |
| Scenarios/runs with successful REMEDIATION | 14 | 27 | 51.8519 |
| Holistic performance within tolerance (best window) | 24 | 31 | 77.4194 |
| Holistic performance within tolerance (worst window) | 9 | 31 | 29.0323 |

## sock-shop

Workload: `front-end`; namespace: `sock-shop`. 29 attempts; 23 selected scenario/run rows; 23 completed selected runs.

Archives: `/Users/home/Universities/ResearchProject/Agents/EvaluationPlatform/Grader/results/sock-shop`. Grades: `/Users/home/Universities/ResearchProject/Agents/EvaluationPlatform/Grader/grades/sock-shop`.

### Aggregate metrics

| Metric | Count | Evaluable denominator | Percent of evaluable |
| --- | --- | --- | --- |
| Successful RCA sessions (score &gt; 0.8) | 39 | 169 | 23.0769 |
| Scenarios/runs with successful RCA | 18 | 22 | 81.8182 |
| Successful REMEDIATION sessions (score &gt; 0.8) | 17 | 103 | 16.5049 |
| Scenarios/runs with successful REMEDIATION | 10 | 19 | 52.6316 |
| Holistic performance within tolerance (best window) | 21 | 23 | 91.3043 |
| Holistic performance within tolerance (worst window) | 9 | 23 | 39.1304 |

### RCA metrics per scenario

| Scenario | Max score | Average score | Sessions during chaos | Scored sessions | Time to first highest score (min) | Timing status |
| --- | --- | --- | --- | --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | 1.0000 | 0.6847 | 9.0000 | 9 | 18.6804 | available |
| sock-shop-node-delay-worker-2-one-hour | 1.0000 | 0.2863 | 10.0000 | 10 | 14.8172 | available |
| sock-shop-node-delay-worker-3-one-hour | 1.0000 | 0.9333 | 3.0000 | 3 | 7.0092 | available |
| sock-shop-node-delay-worker-5-one-hour | 1.0000 | 0.7071 | 7.0000 | 7 | 5.7427 | available |
| sock-shop-node-loss-worker-1-one-hour | 0.7500 | 0.2466 | 11.0000 | 11 | 15.8725 | available |
| sock-shop-node-loss-worker-2-one-hour | 1.0000 | 0.3516 | 8.0000 | 8 | 27.6649 | available |
| sock-shop-node-loss-worker-3-one-hour | 0.9750 | 0.4975 | 5.0000 | 5 | 35.3322 | available |
| sock-shop-node-memory-worker-3-one-hour | Unknown | Unknown | 0.0000 | 0 | Unknown | no_scored_output |
| sock-shop-pod-carts-cpu-all-one-hour | 0.8625 | 0.4275 | 15.0000 | 15 | 6.0092 | available |
| sock-shop-pod-carts-db-memory-all-one-hour | 1.0000 | 0.2167 | 9.0000 | 9 | 9.6047 | available |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | 0.1750 | 0.0583 | 3.0000 | 3 | 25.8818 | available |
| sock-shop-pod-catalogue-cpu-all-one-hour | 0.8125 | 0.5135 | 13.0000 | 13 | 41.6731 | available |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 1.0000 | 0.4542 | 9.0000 | 9 | 8.0544 | available |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 1.0000 | 0.5250 | 6.0000 | 6 | 8.1457 | available |
| sock-shop-pod-orders-capacity-loss-one-hour | 1.0000 | 0.7562 | 6.0000 | 6 | 14.8179 | available |
| sock-shop-pod-orders-cpu-all-one-hour | 1.0000 | 0.7125 | 4.0000 | 4 | 6.0904 | available |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 0.9250 | 0.4361 | 9.0000 | 9 | 12.8546 | available |
| sock-shop-pod-payment-capacity-loss-one-hour | 1.0000 | 0.6107 | 7.0000 | 7 | 15.5826 | available |
| sock-shop-pod-payment-cpu-all-one-hour | 0.6750 | 0.2175 | 10.0000 | 10 | 4.4599 | available |
| sock-shop-pod-shipping-bandwidth-all-one-hour | 0.1125 | 0.1125 | 1.0000 | 1 | 27.9366 | available |
| sock-shop-pod-shipping-memory-all-one-hour | 0.8875 | 0.5781 | 4.0000 | 4 | 13.7518 | available |
| sock-shop-pod-user-cpu-all-one-hour | 1.0000 | 0.5354 | 12.0000 | 12 | 5.2410 | available |
| sock-shop-pod-user-memory-all-one-hour | 1.0000 | 0.4844 | 8.0000 | 8 | 32.6939 | available |

### Remediation metrics per scenario

| Scenario | Max score | Average score | Sessions during chaos | Scored sessions | Time to first highest score (min) | Timing status |
| --- | --- | --- | --- | --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | 0.8750 | 0.4554 | 7.0000 | 7 | 56.7648 | available |
| sock-shop-node-delay-worker-2-one-hour | 0.6750 | 0.1536 | 8.0000 | 7 | 17.4683 | available |
| sock-shop-node-delay-worker-3-one-hour | 1.0000 | 0.6000 | 3.0000 | 3 | 8.5571 | available |
| sock-shop-node-delay-worker-5-one-hour | 1.0000 | 0.6850 | 5.0000 | 5 | 13.8911 | available |
| sock-shop-node-loss-worker-1-one-hour | 0.7500 | 0.3607 | 8.0000 | 7 | 17.7304 | available |
| sock-shop-node-loss-worker-2-one-hour | 1.0000 | 0.3906 | 8.0000 | 8 | 30.8992 | available |
| sock-shop-node-loss-worker-3-one-hour | 0.3875 | 0.2375 | 3.0000 | 3 | 12.0141 | available |
| sock-shop-node-memory-worker-3-one-hour | Unknown | Unknown | 0.0000 | 0 | Unknown | no_scored_output |
| sock-shop-pod-carts-cpu-all-one-hour | Unknown | Unknown | 0.0000 | 0 | Unknown | no_scored_output |
| sock-shop-pod-carts-db-memory-all-one-hour | 0.7000 | 0.1167 | 9.0000 | 6 | 10.6888 | available |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | Unknown | Unknown | 0.0000 | 0 | Unknown | no_scored_output |
| sock-shop-pod-catalogue-cpu-all-one-hour | 1.0000 | 0.8958 | 3.0000 | 3 | 10.8707 | available |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 0.3375 | 0.1344 | 8.0000 | 8 | 32.0962 | available |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 1.0000 | 0.4396 | 6.0000 | 6 | 3.7573 | available |
| sock-shop-pod-orders-capacity-loss-one-hour | 0.3500 | 0.1500 | 6.0000 | 5 | 55.9880 | available |
| sock-shop-pod-orders-cpu-all-one-hour | 0.9125 | 0.9125 | 1.0000 | 1 | 8.9403 | available |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 0.7375 | 0.1500 | 9.0000 | 8 | 15.3243 | available |
| sock-shop-pod-payment-capacity-loss-one-hour | 0.4625 | 0.1161 | 7.0000 | 7 | 11.3433 | available |
| sock-shop-pod-payment-cpu-all-one-hour | 0.0000 | 0.0000 | 8.0000 | 8 | 11.4271 | available |
| sock-shop-pod-shipping-bandwidth-all-one-hour | Unknown | Unknown | 0.0000 | 0 | Unknown | no_scored_output |
| sock-shop-pod-shipping-memory-all-one-hour | 1.0000 | 0.7500 | 3.0000 | 3 | 15.7505 | available |
| sock-shop-pod-user-cpu-all-one-hour | 0.9625 | 0.4375 | 4.0000 | 4 | 35.2277 | available |
| sock-shop-pod-user-memory-all-one-hour | 1.0000 | 0.7375 | 4.0000 | 4 | 34.4721 | available |

### Baseline reference

| Scenario | P95 (s) | 5xx (requests/s) |
| --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | 0.0948 | 0.0000 |
| sock-shop-node-delay-worker-2-one-hour | 0.0960 | 0.0000 |
| sock-shop-node-delay-worker-3-one-hour | 0.0955 | 0.0000 |
| sock-shop-node-delay-worker-5-one-hour | 0.0953 | 0.0000 |
| sock-shop-node-loss-worker-1-one-hour | 0.0958 | 0.0000 |
| sock-shop-node-loss-worker-2-one-hour | 0.0949 | 0.0000 |
| sock-shop-node-loss-worker-3-one-hour | 0.0946 | 0.0000 |
| sock-shop-node-memory-worker-3-one-hour | 0.0953 | 0.0000 |
| sock-shop-pod-carts-cpu-all-one-hour | 0.0941 | 0.0000 |
| sock-shop-pod-carts-db-memory-all-one-hour | 0.0929 | 0.0000 |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | 0.0937 | 0.0000 |
| sock-shop-pod-catalogue-cpu-all-one-hour | 0.0950 | 0.0000 |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 0.4451 | 0.0552 |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 0.4440 | 0.0248 |
| sock-shop-pod-orders-capacity-loss-one-hour | 0.0940 | 0.0000 |
| sock-shop-pod-orders-cpu-all-one-hour | 0.0945 | 0.0000 |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 0.4704 | 0.0000 |
| sock-shop-pod-payment-capacity-loss-one-hour | 0.0940 | 0.0000 |
| sock-shop-pod-payment-cpu-all-one-hour | 0.0963 | 0.0000 |
| sock-shop-pod-shipping-bandwidth-all-one-hour | 0.0929 | 0.0000 |
| sock-shop-pod-shipping-memory-all-one-hour | 0.0934 | 0.0000 |
| sock-shop-pod-user-cpu-all-one-hour | 0.0968 | 0.0000 |
| sock-shop-pod-user-memory-all-one-hour | 0.0926 | 0.0000 |

### Best rolling window versus baseline

| Scenario | P95 (s) | P95 difference (s) | P95 change (%) | 5xx (requests/s) | 5xx difference (requests/s) | 5xx change (%) | Within tolerance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | 0.0696 | -0.0253 | -26.6388 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-delay-worker-2-one-hour | 0.0786 | -0.0175 | -18.1801 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-delay-worker-3-one-hour | 0.0950 | -0.0004 | -0.4584 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-delay-worker-5-one-hour | 0.0930 | -0.0023 | -2.4273 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-loss-worker-1-one-hour | 0.1403 | 0.0445 | 46.4773 | 0.0000 | 0.0000 | Unknown | No |
| sock-shop-node-loss-worker-2-one-hour | 0.1000 | 0.0051 | 5.4248 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-loss-worker-3-one-hour | 0.0946 | -0.0000 | -0.0406 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-memory-worker-3-one-hour | 0.0931 | -0.0022 | -2.3218 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-carts-cpu-all-one-hour | 0.0930 | -0.0011 | -1.1722 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-carts-db-memory-all-one-hour | 0.0923 | -0.0006 | -0.6423 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | 0.0931 | -0.0006 | -0.5975 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-catalogue-cpu-all-one-hour | 0.0979 | 0.0029 | 3.0097 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 0.1224 | -0.3227 | -72.5009 | 0.0000 | -0.0552 | -100.0000 | Yes |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 0.1010 | -0.3431 | -77.2588 | 0.0000 | -0.0248 | -100.0000 | Yes |
| sock-shop-pod-orders-capacity-loss-one-hour | 0.1070 | 0.0130 | 13.8095 | 0.1133 | 0.1133 | Unknown | Yes |
| sock-shop-pod-orders-cpu-all-one-hour | 0.1031 | 0.0086 | 9.0770 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 0.0950 | -0.3754 | -79.8102 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-payment-capacity-loss-one-hour | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | No |
| sock-shop-pod-payment-cpu-all-one-hour | 0.0953 | -0.0010 | -1.0402 | 0.0251 | 0.0251 | Unknown | Yes |
| sock-shop-pod-shipping-bandwidth-all-one-hour | 0.0917 | -0.0011 | -1.1932 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-shipping-memory-all-one-hour | 0.0925 | -0.0009 | -0.9977 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-user-cpu-all-one-hour | 0.0981 | 0.0013 | 1.3228 | 0.0377 | 0.0377 | Unknown | Yes |
| sock-shop-pod-user-memory-all-one-hour | 0.0922 | -0.0005 | -0.4912 | 0.0000 | 0.0000 | Unknown | Yes |

### Worst rolling window versus baseline

| Scenario | P95 (s) | P95 difference (s) | P95 change (%) | 5xx (requests/s) | 5xx difference (requests/s) | 5xx change (%) | Within tolerance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | 0.0950 | 0.0002 | 0.1744 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-node-delay-worker-2-one-hour | 4.1130 | 4.0170 | 4182.4301 | 0.0000 | 0.0000 | Unknown | No |
| sock-shop-node-delay-worker-3-one-hour | 3.5559 | 3.4604 | 3624.8194 | 0.0048 | 0.0048 | Unknown | No |
| sock-shop-node-delay-worker-5-one-hour | 1.4021 | 1.3069 | 1371.5351 | 0.0492 | 0.0492 | Unknown | No |
| sock-shop-node-loss-worker-1-one-hour | 0.7965 | 0.7007 | 731.4407 | 0.1046 | 0.1046 | Unknown | No |
| sock-shop-node-loss-worker-2-one-hour | 0.5715 | 0.4766 | 502.4162 | 1.5537 | 1.5537 | Unknown | No |
| sock-shop-node-loss-worker-3-one-hour | 0.5123 | 0.4177 | 441.5719 | 0.2013 | 0.2013 | Unknown | No |
| sock-shop-node-memory-worker-3-one-hour | 0.0947 | -0.0006 | -0.6195 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-carts-cpu-all-one-hour | 0.0939 | -0.0002 | -0.1759 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-carts-db-memory-all-one-hour | 0.1762 | 0.0833 | 89.6514 | 0.6026 | 0.6026 | Unknown | No |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | 0.0950 | 0.0013 | 1.3637 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-catalogue-cpu-all-one-hour | 0.1053 | 0.0103 | 10.8486 | 0.9758 | 0.9758 | Unknown | No |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 0.4015 | -0.0435 | -9.7832 | 0.2246 | 0.1694 | 307.1534 | Yes |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 0.6650 | 0.2210 | 49.7740 | 0.0000 | -0.0248 | -100.0000 | No |
| sock-shop-pod-orders-capacity-loss-one-hour | 0.1688 | 0.0748 | 79.4849 | 5.9643 | 5.9643 | Unknown | No |
| sock-shop-pod-orders-cpu-all-one-hour | 0.1796 | 0.0851 | 90.0576 | 0.0000 | 0.0000 | Unknown | No |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 0.5216 | 0.0513 | 10.9051 | 0.0837 | 0.0837 | Unknown | Yes |
| sock-shop-pod-payment-capacity-loss-one-hour | 0.5304 | 0.4364 | 464.1696 | 13.3714 | 13.3714 | Unknown | No |
| sock-shop-pod-payment-cpu-all-one-hour | 0.1957 | 0.0994 | 103.2397 | 0.0155 | 0.0155 | Unknown | No |
| sock-shop-pod-shipping-bandwidth-all-one-hour | 0.0932 | 0.0003 | 0.3366 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-shipping-memory-all-one-hour | 0.0955 | 0.0021 | 2.2665 | 0.0000 | 0.0000 | Unknown | Yes |
| sock-shop-pod-user-cpu-all-one-hour | 0.1105 | 0.0138 | 14.2075 | 0.0435 | 0.0435 | Unknown | Yes |
| sock-shop-pod-user-memory-all-one-hour | 0.1119 | 0.0193 | 20.8081 | 0.2717 | 0.2717 | Unknown | No |

### Window evidence and missing data

| Scenario | Window status | Reason | Best start (UTC) | Best end (UTC) | Worst start (UTC) | Worst end (UTC) | Baseline imputed 5xx samples | Best imputed 5xx samples | Worst imputed 5xx samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | evaluable | Unknown | 2026-09-16T06:14:52.367841+00:00 | 2026-09-16T06:19:52.367841+00:00 | 2026-09-16T06:01:22.367841+00:00 | 2026-09-16T06:06:22.367841+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-node-delay-worker-2-one-hour | evaluable | Unknown | 2026-09-15T09:49:36.458569+00:00 | 2026-09-15T09:54:36.458569+00:00 | 2026-09-15T09:33:51.458569+00:00 | 2026-09-15T09:38:51.458569+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-node-delay-worker-3-one-hour | evaluable | Unknown | 2026-09-15T08:09:54.666178+00:00 | 2026-09-15T08:14:54.666178+00:00 | 2026-09-15T07:42:09.666178+00:00 | 2026-09-15T07:47:09.666178+00:00 | 100.0000 | 20.0000 | 0.0000 |
| sock-shop-node-delay-worker-5-one-hour | evaluable | Unknown | 2026-09-15T11:42:06.416225+00:00 | 2026-09-15T11:47:06.416225+00:00 | 2026-09-15T11:27:06.416225+00:00 | 2026-09-15T11:32:06.416225+00:00 | 100.0000 | 20.0000 | 0.0000 |
| sock-shop-node-loss-worker-1-one-hour | evaluable | Unknown | 2026-09-15T13:54:03.422098+00:00 | 2026-09-15T13:59:03.422098+00:00 | 2026-09-15T13:20:18.422098+00:00 | 2026-09-15T13:25:18.422098+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-node-loss-worker-2-one-hour | evaluable | Unknown | 2026-09-15T16:01:27.216173+00:00 | 2026-09-15T16:06:27.216173+00:00 | 2026-09-15T15:14:57.216173+00:00 | 2026-09-15T15:19:57.216173+00:00 | 100.0000 | 0.0000 | 0.0000 |
| sock-shop-node-loss-worker-3-one-hour | evaluable | Unknown | 2026-09-15T17:54:04.427557+00:00 | 2026-09-15T17:59:04.427557+00:00 | 2026-09-15T17:04:49.427557+00:00 | 2026-09-15T17:09:49.427557+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-node-memory-worker-3-one-hour | evaluable | Unknown | 2026-09-16T07:31:57.792418+00:00 | 2026-09-16T07:36:57.792418+00:00 | 2026-09-16T07:55:42.792418+00:00 | 2026-09-16T08:00:42.792418+00:00 | 100.0000 | 20.0000 | 20.0000 |
| sock-shop-pod-carts-cpu-all-one-hour | evaluable | Unknown | 2026-09-15T19:09:20.267864+00:00 | 2026-09-15T19:14:20.267864+00:00 | 2026-09-15T18:53:20.267864+00:00 | 2026-09-15T18:58:20.267864+00:00 | 100.0000 | 20.0000 | 20.0000 |
| sock-shop-pod-carts-db-memory-all-one-hour | evaluable | Unknown | 2026-09-16T15:20:53.098384+00:00 | 2026-09-16T15:25:53.098384+00:00 | 2026-09-16T14:39:53.098384+00:00 | 2026-09-16T14:44:53.098384+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | evaluable | Unknown | 2026-09-16T13:35:09.808840+00:00 | 2026-09-16T13:40:09.808840+00:00 | 2026-09-16T12:59:39.808840+00:00 | 2026-09-16T13:04:39.808840+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-catalogue-cpu-all-one-hour | evaluable | Unknown | 2026-09-16T00:34:20.809979+00:00 | 2026-09-16T00:39:20.809979+00:00 | 2026-09-16T01:21:35.809979+00:00 | 2026-09-16T01:26:35.809979+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | evaluable | Unknown | 2026-09-17T10:31:25.835915+00:00 | 2026-09-17T10:36:25.835915+00:00 | 2026-09-17T10:08:25.835915+00:00 | 2026-09-17T10:13:25.835915+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | evaluable | Unknown | 2026-09-17T06:09:04.873079+00:00 | 2026-09-17T06:14:04.873079+00:00 | 2026-09-17T05:49:04.873079+00:00 | 2026-09-17T05:54:04.873079+00:00 | 0.0000 | 20.0000 | 0.0000 |
| sock-shop-pod-orders-capacity-loss-one-hour | evaluable | Unknown | 2026-09-16T11:27:26.210516+00:00 | 2026-09-16T11:32:26.210516+00:00 | 2026-09-16T11:07:11.210516+00:00 | 2026-09-16T11:12:11.210516+00:00 | 100.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-orders-cpu-all-one-hour | evaluable | Unknown | 2026-09-15T20:45:05.869628+00:00 | 2026-09-15T20:50:05.869628+00:00 | 2026-09-15T20:55:35.869628+00:00 | 2026-09-15T21:00:35.869628+00:00 | 100.0000 | 20.0000 | 20.0000 |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | evaluable | Unknown | 2026-09-17T08:38:24.520414+00:00 | 2026-09-17T08:43:24.520414+00:00 | 2026-09-17T07:48:24.520414+00:00 | 2026-09-17T07:53:24.520414+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-payment-capacity-loss-one-hour | partially_evaluable | No covered window meets the mean 5xx-rate threshold; worst window remains available. | Unknown | Unknown | 2026-09-16T20:57:03.799139+00:00 | 2026-09-16T21:02:03.799139+00:00 | 0.0000 | Unknown | 0.0000 |
| sock-shop-pod-payment-cpu-all-one-hour | evaluable | Unknown | 2026-09-16T03:34:07.627322+00:00 | 2026-09-16T03:39:07.627322+00:00 | 2026-09-16T03:39:07.627322+00:00 | 2026-09-16T03:44:07.627322+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-shipping-bandwidth-all-one-hour | evaluable | Unknown | 2026-09-16T18:30:10.448697+00:00 | 2026-09-16T18:35:10.448697+00:00 | 2026-09-16T19:16:10.448697+00:00 | 2026-09-16T19:21:10.448697+00:00 | 100.0000 | 20.0000 | 0.0000 |
| sock-shop-pod-shipping-memory-all-one-hour | evaluable | Unknown | 2026-09-16T09:34:48.129797+00:00 | 2026-09-16T09:39:48.129797+00:00 | 2026-09-16T09:10:18.129797+00:00 | 2026-09-16T09:15:18.129797+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-user-cpu-all-one-hour | evaluable | Unknown | 2026-09-15T22:45:49.814594+00:00 | 2026-09-15T22:50:49.814594+00:00 | 2026-09-15T22:53:34.814594+00:00 | 2026-09-15T22:58:34.814594+00:00 | 0.0000 | 0.0000 | 0.0000 |
| sock-shop-pod-user-memory-all-one-hour | evaluable | Unknown | 2026-09-16T16:39:35.763137+00:00 | 2026-09-16T16:44:35.763137+00:00 | 2026-09-16T17:05:05.763137+00:00 | 2026-09-16T17:10:05.763137+00:00 | 100.0000 | 20.0000 | 0.0000 |

### Attempts and exclusions

| Scenario | Run | Selected | Run status | Grade status | Chaos boundaries | Exported RCA | Excluded RCA | Exported remediation | Excluded remediation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sock-shop-node-cpu-worker-2-one-hour | 20260916-044232-sock-shop-node-cpu-worker-2-one-hour-e7fb3d20 | Yes | completed | graded | available | 12 | 3.0000 | 9 | 2.0000 |
| sock-shop-node-delay-worker-2-one-hour | 20260915-085323-sock-shop-node-delay-worker-2-one-hour-6d3be870 | Yes | completed | graded | available | 13 | 3.0000 | 10 | 2.0000 |
| sock-shop-node-delay-worker-3-one-hour | 20260915-070028-sock-shop-node-delay-worker-3-one-hour-f8cea5b7 | Yes | completed | graded | available | 4 | 1.0000 | 4 | 1.0000 |
| sock-shop-node-delay-worker-5-one-hour | 20260915-104631-sock-shop-node-delay-worker-5-one-hour-c594d88b | Yes | completed | graded | available | 10 | 3.0000 | 7 | 2.0000 |
| sock-shop-node-loss-worker-1-one-hour | 20260915-123927-sock-shop-node-loss-worker-1-one-hour-0a72f966 | Yes | completed | graded | available | 11 | 0.0000 | 8 | 0.0000 |
| sock-shop-node-loss-worker-2-one-hour | 20260915-143132-sock-shop-node-loss-worker-2-one-hour-643fe312 | Yes | completed | graded | available | 11 | 3.0000 | 10 | 2.0000 |
| sock-shop-node-loss-worker-3-one-hour | 20260915-162308-sock-shop-node-loss-worker-3-one-hour-9fb87ae1 | Yes | completed | graded | available | 5 | 0.0000 | 3 | 0.0000 |
| sock-shop-node-memory-worker-3-one-hour | 20260916-063430-sock-shop-node-memory-worker-3-one-hour-7bec91aa | Yes | completed | graded | available | 2 | 2.0000 | 2 | 2.0000 |
| sock-shop-pod-carts-cpu-all-one-hour | 20260915-181504-sock-shop-pod-carts-cpu-all-one-hour-d9ce8582 | Yes | completed | graded | available | 19 | 4.0000 | 0 | 0.0000 |
| sock-shop-pod-carts-db-memory-all-one-hour | 20260916-140121-sock-shop-pod-carts-db-memory-all-one-hour-d1b6af93 | Yes | completed | graded | available | 12 | 3.0000 | 11 | 2.0000 |
| sock-shop-pod-catalogue-bandwidth-all-one-hour | 20260916-120946-sock-shop-pod-catalogue-bandwidth-all-one-hour-5602bb98 | Yes | completed | graded | available | 6 | 3.0000 | 2 | 2.0000 |
| sock-shop-pod-catalogue-cpu-all-one-hour | 20260915-235020-sock-shop-pod-catalogue-cpu-all-one-hour-72f06623 | Yes | completed | graded | available | 15 | 2.0000 | 5 | 2.0000 |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 20260917-041115-sock-shop-pod-catalogue-cpu-headroom-all-one-hour-de251a86 | No | failed | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| sock-shop-pod-catalogue-cpu-headroom-all-one-hour | 20260917-085658-sock-shop-pod-catalogue-cpu-headroom-all-one-hour-a4bb7faa | Yes | completed | graded | available | 10 | 1.0000 | 8 | 0.0000 |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 20260917-031131-sock-shop-pod-front-end-cpu-headroom-all-one-hour-9893d7f8 | No | failed | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 20260917-034402-sock-shop-pod-front-end-cpu-headroom-all-one-hour-cfd30866 | No | failed | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 20260917-044503-sock-shop-pod-front-end-cpu-headroom-all-one-hour-0f633733 | No | interrupted | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| sock-shop-pod-front-end-cpu-headroom-all-one-hour | 20260917-050755-sock-shop-pod-front-end-cpu-headroom-all-one-hour-ca4e5837 | Yes | completed | graded | available | 8 | 2.0000 | 6 | 0.0000 |
| sock-shop-pod-orders-capacity-loss-one-hour | 20260916-101803-sock-shop-pod-orders-capacity-loss-one-hour-24096e3c | Yes | completed | graded | available | 8 | 2.0000 | 7 | 1.0000 |
| sock-shop-pod-orders-cpu-all-one-hour | 20260915-200700-sock-shop-pod-orders-cpu-all-one-hour-e659c343 | Yes | completed | graded | available | 6 | 2.0000 | 2 | 1.0000 |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 20260917-032555-sock-shop-pod-orders-cpu-headroom-all-one-hour-cfa8ccc1 | No | failed | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 20260917-035706-sock-shop-pod-orders-cpu-headroom-all-one-hour-578b15e0 | No | failed | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| sock-shop-pod-orders-cpu-headroom-all-one-hour | 20260917-070236-sock-shop-pod-orders-cpu-headroom-all-one-hour-e0f89a80 | Yes | completed | graded | available | 12 | 3.0000 | 11 | 2.0000 |
| sock-shop-pod-payment-capacity-loss-one-hour | 20260916-193636-sock-shop-pod-payment-capacity-loss-one-hour-fe747c4d | Yes | completed | graded | available | 9 | 2.0000 | 8 | 1.0000 |
| sock-shop-pod-payment-cpu-all-one-hour | 20260916-025047-sock-shop-pod-payment-cpu-all-one-hour-a72bcbd1 | Yes | completed | graded | available | 11 | 1.0000 | 9 | 1.0000 |
| sock-shop-pod-shipping-bandwidth-all-one-hour | 20260916-174500-sock-shop-pod-shipping-bandwidth-all-one-hour-02fe1a50 | Yes | completed | graded | available | 3 | 2.0000 | 1 | 1.0000 |
| sock-shop-pod-shipping-memory-all-one-hour | 20260916-082631-sock-shop-pod-shipping-memory-all-one-hour-a23a2506 | Yes | completed | graded | available | 6 | 2.0000 | 4 | 1.0000 |
| sock-shop-pod-user-cpu-all-one-hour | 20260915-215839-sock-shop-pod-user-cpu-all-one-hour-76bd5381 | Yes | completed | graded | available | 15 | 3.0000 | 5 | 1.0000 |
| sock-shop-pod-user-memory-all-one-hour | 20260916-155256-sock-shop-pod-user-memory-all-one-hour-aa79aa40 | Yes | completed | graded | available | 11 | 3.0000 | 5 | 1.0000 |

## online-boutique

Workload: `frontend`; namespace: `online-boutique`. 10 attempts; 10 selected scenario/run rows; 8 completed selected runs.

Archives: `/Users/home/Universities/ResearchProject/Agents/EvaluationPlatform/Grader/results/online-boutique`. Grades: `/Users/home/Universities/ResearchProject/Agents/EvaluationPlatform/Grader/grades/online-boutique`.

### Aggregate metrics

| Metric | Count | Evaluable denominator | Percent of evaluable |
| --- | --- | --- | --- |
| Successful RCA sessions (score &gt; 0.8) | 18 | 60 | 30.0000 |
| Scenarios/runs with successful RCA | 7 | 8 | 87.5000 |
| Successful REMEDIATION sessions (score &gt; 0.8) | 5 | 32 | 15.6250 |
| Scenarios/runs with successful REMEDIATION | 4 | 8 | 50.0000 |
| Holistic performance within tolerance (best window) | 3 | 8 | 37.5000 |
| Holistic performance within tolerance (worst window) | 0 | 8 | 0.0000 |

### RCA metrics per scenario

| Scenario | Max score | Average score | Sessions during chaos | Scored sessions | Time to first highest score (min) | Timing status |
| --- | --- | --- | --- | --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | 1.0000 | 0.4562 | 8.0000 | 8 | 12.8564 | available |
| online-boutique-node-delay-worker-3-one-hour | 1.0000 | 0.4000 | 11.0000 | 11 | 7.5197 | available |
| online-boutique-node-delay-worker-5-one-hour | 1.0000 | 0.1798 | 13.0000 | 13 | 14.6248 | available |
| online-boutique-node-loss-worker-1-one-hour | 1.0000 | 0.4900 | 5.0000 | 5 | 13.3613 | available |
| online-boutique-node-loss-worker-2-one-hour | 0.5125 | 0.2525 | 5.0000 | 5 | 7.3730 | available |
| online-boutique-node-loss-worker-3-one-hour | 1.0000 | 0.8844 | 4.0000 | 4 | 57.4685 | available |
| online-boutique-pod-cartservice-cpu-all-one-hour | Unknown | Unknown | Unknown | 0 | Unknown | no_scored_output |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | 1.0000 | 0.7804 | 7.0000 | 7 | 10.0809 | available |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | Unknown | Unknown | Unknown | 0 | Unknown | no_scored_output |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | 1.0000 | 0.4464 | 7.0000 | 7 | 18.6503 | available |

### Remediation metrics per scenario

| Scenario | Max score | Average score | Sessions during chaos | Scored sessions | Time to first highest score (min) | Timing status |
| --- | --- | --- | --- | --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | 1.0000 | 0.4562 | 7.0000 | 6 | 13.9720 | available |
| online-boutique-node-delay-worker-3-one-hour | 0.3000 | 0.1500 | 6.0000 | 2 | 32.1212 | available |
| online-boutique-node-delay-worker-5-one-hour | 0.9625 | 0.8250 | 2.0000 | 2 | 16.3838 | available |
| online-boutique-node-loss-worker-1-one-hour | 0.1000 | 0.0500 | 5.0000 | 2 | 8.6362 | available |
| online-boutique-node-loss-worker-2-one-hour | 0.5625 | 0.3219 | 4.0000 | 4 | 9.0610 | available |
| online-boutique-node-loss-worker-3-one-hour | 1.0000 | 0.5958 | 4.0000 | 3 | 58.4307 | available |
| online-boutique-pod-cartservice-cpu-all-one-hour | Unknown | Unknown | Unknown | 0 | Unknown | no_scored_output |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | 0.9625 | 0.5196 | 7.0000 | 7 | 30.2081 | available |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | Unknown | Unknown | Unknown | 0 | Unknown | no_scored_output |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | 0.6875 | 0.1417 | 6.0000 | 6 | 25.5566 | available |

### Baseline reference

| Scenario | P95 (s) | 5xx (requests/s) |
| --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | 0.1042 | 0.0280 |
| online-boutique-node-delay-worker-3-one-hour | 0.1029 | 0.0278 |
| online-boutique-node-delay-worker-5-one-hour | 0.0994 | 0.0278 |
| online-boutique-node-loss-worker-1-one-hour | 0.1005 | 0.0234 |
| online-boutique-node-loss-worker-2-one-hour | 0.1054 | 0.0258 |
| online-boutique-node-loss-worker-3-one-hour | 0.0983 | 0.0220 |
| online-boutique-pod-cartservice-cpu-all-one-hour | Unknown | Unknown |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | 0.0999 | 0.0272 |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | Unknown | Unknown |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | 0.0981 | 0.0288 |

### Best rolling window versus baseline

| Scenario | P95 (s) | P95 difference (s) | P95 change (%) | 5xx (requests/s) | 5xx difference (requests/s) | 5xx change (%) | Within tolerance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | 0.0974 | -0.0069 | -6.5869 | 0.0234 | -0.0046 | -16.5569 | Yes |
| online-boutique-node-delay-worker-3-one-hour | 0.1068 | 0.0040 | 3.8736 | 0.0346 | 0.0068 | 24.5431 | Yes |
| online-boutique-node-delay-worker-5-one-hour | 0.0938 | -0.0056 | -5.5904 | 0.0377 | 0.0099 | 35.7968 | Yes |
| online-boutique-node-loss-worker-1-one-hour | 0.4451 | 0.3446 | 342.7233 | 0.0142 | -0.0093 | -39.5383 | No |
| online-boutique-node-loss-worker-2-one-hour | 0.3854 | 0.2801 | 265.7977 | 0.0326 | 0.0069 | 26.6063 | No |
| online-boutique-node-loss-worker-3-one-hour | 0.1682 | 0.0699 | 71.1405 | 0.0548 | 0.0328 | 148.9460 | No |
| online-boutique-pod-cartservice-cpu-all-one-hour | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | 0.1505 | 0.0506 | 50.6482 | 0.0299 | 0.0027 | 9.7448 | No |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | 0.1446 | 0.0466 | 47.4917 | 0.0286 | -0.0002 | -0.7248 | No |

### Worst rolling window versus baseline

| Scenario | P95 (s) | P95 difference (s) | P95 change (%) | 5xx (requests/s) | 5xx difference (requests/s) | 5xx change (%) | Within tolerance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | 4.5112 | 4.4069 | 4227.4667 | 0.0199 | -0.0081 | -29.1021 | No |
| online-boutique-node-delay-worker-3-one-hour | 4.0313 | 3.9285 | 3819.5068 | 0.0236 | -0.0042 | -14.9631 | No |
| online-boutique-node-delay-worker-5-one-hour | 2.5912 | 2.4918 | 2508.0744 | 0.0201 | -0.0076 | -27.5341 | No |
| online-boutique-node-loss-worker-1-one-hour | 0.8341 | 0.7335 | 729.5500 | 0.9168 | 0.8934 | 3814.2920 | No |
| online-boutique-node-loss-worker-2-one-hour | 0.5517 | 0.4463 | 423.5849 | 0.0451 | 0.0193 | 75.0645 | No |
| online-boutique-node-loss-worker-3-one-hour | 0.5588 | 0.4605 | 468.5653 | 0.0390 | 0.0170 | 77.2754 | No |
| online-boutique-pod-cartservice-cpu-all-one-hour | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | 0.2551 | 0.1553 | 155.4678 | 0.0431 | 0.0159 | 58.4386 | No |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | 0.2503 | 0.1522 | 155.1951 | 0.0221 | -0.0066 | -23.0774 | No |

### Window evidence and missing data

| Scenario | Window status | Reason | Best start (UTC) | Best end (UTC) | Worst start (UTC) | Worst end (UTC) | Baseline imputed 5xx samples | Best imputed 5xx samples | Worst imputed 5xx samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | evaluable | Unknown | 2026-09-17T14:50:53.657352+00:00 | 2026-09-17T14:55:53.657352+00:00 | 2026-09-17T14:32:53.657352+00:00 | 2026-09-17T14:37:53.657352+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-node-delay-worker-3-one-hour | evaluable | Unknown | 2026-09-17T13:35:55.604180+00:00 | 2026-09-17T13:40:55.604180+00:00 | 2026-09-17T12:43:55.604180+00:00 | 2026-09-17T12:48:55.604180+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-node-delay-worker-5-one-hour | evaluable | Unknown | 2026-09-17T16:48:12.969092+00:00 | 2026-09-17T16:53:12.969092+00:00 | 2026-09-17T16:22:42.969092+00:00 | 2026-09-17T16:27:42.969092+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-node-loss-worker-1-one-hour | evaluable | Unknown | 2026-09-17T18:09:08.351993+00:00 | 2026-09-17T18:14:08.351993+00:00 | 2026-09-17T18:12:08.351993+00:00 | 2026-09-17T18:17:08.351993+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-node-loss-worker-2-one-hour | evaluable | Unknown | 2026-09-17T20:51:05.235141+00:00 | 2026-09-17T20:56:05.235141+00:00 | 2026-09-17T19:58:35.235141+00:00 | 2026-09-17T20:03:35.235141+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-node-loss-worker-3-one-hour | evaluable | Unknown | 2026-09-17T22:40:22.378180+00:00 | 2026-09-17T22:45:22.378180+00:00 | 2026-09-17T22:11:07.378180+00:00 | 2026-09-17T22:16:07.378180+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-pod-cartservice-cpu-all-one-hour | not_evaluable | missing timestamp | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | evaluable | Unknown | 2026-09-17T23:38:08.814562+00:00 | 2026-09-17T23:43:08.814562+00:00 | 2026-09-17T23:51:08.814562+00:00 | 2026-09-17T23:56:08.814562+00:00 | 0.0000 | 0.0000 | 0.0000 |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | not_evaluable | missing recorded chaos intervals | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | evaluable | Unknown | 2026-09-18T01:27:14.477439+00:00 | 2026-09-18T01:32:14.477439+00:00 | 2026-09-18T01:57:59.477439+00:00 | 2026-09-18T02:02:59.477439+00:00 | 0.0000 | 0.0000 | 0.0000 |

### Attempts and exclusions

| Scenario | Run | Selected | Run status | Grade status | Chaos boundaries | Exported RCA | Excluded RCA | Exported remediation | Excluded remediation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| online-boutique-node-delay-worker-2-one-hour | 20260917-135646-online-boutique-node-delay-worker-2-one-hour-e5daaf4c | Yes | completed | graded | available | 9 | 1.0000 | 7 | 0.0000 |
| online-boutique-node-delay-worker-3-one-hour | 20260917-120727-online-boutique-node-delay-worker-3-one-hour-00dd0d05 | Yes | completed | graded | available | 14 | 3.0000 | 6 | 0.0000 |
| online-boutique-node-delay-worker-5-one-hour | 20260917-154538-online-boutique-node-delay-worker-5-one-hour-77c0a6e6 | Yes | completed | graded | available | 16 | 3.0000 | 2 | 0.0000 |
| online-boutique-node-loss-worker-1-one-hour | 20260917-173444-online-boutique-node-loss-worker-1-one-hour-4c1b1ce8 | Yes | completed | graded | available | 7 | 2.0000 | 6 | 1.0000 |
| online-boutique-node-loss-worker-2-one-hour | 20260917-192242-online-boutique-node-loss-worker-2-one-hour-de0ca92c | Yes | completed | graded | available | 6 | 1.0000 | 4 | 0.0000 |
| online-boutique-node-loss-worker-3-one-hour | 20260917-211100-online-boutique-node-loss-worker-3-one-hour-447da855 | Yes | completed | graded | available | 6 | 2.0000 | 5 | 1.0000 |
| online-boutique-pod-cartservice-cpu-all-one-hour | 20260917-225912-online-boutique-pod-cartservice-cpu-all-one-hour-d8d67715 | Yes | failed | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| online-boutique-pod-checkoutservice-cpu-all-one-hour | 20260917-230350-online-boutique-pod-checkoutservice-cpu-all-one-hour-0c3ef708 | Yes | completed | graded | available | 7 | 0.0000 | 7 | 0.0000 |
| online-boutique-pod-productcatalogservice-cpu-all-one-hour | 20260918-024050-online-boutique-pod-productcatalogservice-cpu-all-one-hour-f222f4b7 | Yes | interrupted | graded | missing_or_invalid_chaos_boundaries | 0 | Unknown | 0 | Unknown |
| online-boutique-pod-recommendationservice-cpu-all-one-hour | 20260918-005141-online-boutique-pod-recommendationservice-cpu-all-one-hour-ea84314b | Yes | completed | graded | available | 7 | 0.0000 | 7 | 1.0000 |

## teastore

_No archived runs or grades available yet._
