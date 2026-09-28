# IncidentBench: analysis of compiled experimental results

Prepared 28 September 2026. This report analyzes the current local `results/` and `grades/` snapshot using the metric definitions and default settings in [`eda/report.ipynb`](eda/report.ipynb) and [`eda/report_metrics.py`](eda/report_metrics.py). It is a descriptive analysis of the IncidentBench reference SRE agent system within the benchmark, intended to support the paper and thesis results and discussion. It does not modify the manuscript, rerun experiments, or invoke the semantic judge.

## 1. Main findings

The strongest result is the separation between **attaining a good diagnosis, producing an appropriate remediation report, and observing acceptable frontend performance**. Across 65 selected completed scenario runs, 46 of 64 scenarios with scored RCA outputs attained a score above 0.8 (71.9%), while 27 of 60 with scored remediation outputs did so (45.0%). Only 119 of 503 RCA outputs (23.7%) and 39 of 351 remediation outputs (11.1%) exceeded the threshold. High scenario maxima therefore describe intermittent attainment, not consistently strong responses.

Frontend behavior tells a different story. Best-Window Tolerance holds in 44/65 runs (67.7%). This indicates a favorable selected period in many runs, while the semantic output counts describe the quality of diagnosis and remediation reports. The two observations should remain separate assessment paths.

The most informative scenario contrasts are:

- **Node delay:** all nine scenarios attain successful RCA and a best window within tolerance. This shows diagnostic attainment alongside favorable selected frontend periods, without establishing sustained recovery.
- **Node packet loss:** only 4/9 attain successful RCA, 2/9 successful remediation, and 2/9 Best-Window Tolerance. This family is difficult at multiple stages in this dataset.
- **Pod bandwidth restrictions:** none of five scenarios attains successful RCA; no successful remediation is observed, and three have no in-scope remediation output. Nevertheless, four have best windows within tolerance. Acceptable frontend windows do not establish successful diagnosis or corrective action.
- **CPU headroom and recurring capacity loss:** RCA often reaches the semantic threshold, but remediation seldom does. Capacity, controller behavior, scheduling constraints, and scenario-specific action requirements matter after localization.

The cross-application analysis in Sections 6.1–6.7 explains why application totals should be interpreted through matching fault families and their operating conditions. Identical node or bandwidth settings expose different services and investigation signals; headroom profiles can also change the baseline against which improvement is measured. These concrete differences help explain contrasting outcomes without attributing them to the application name alone.

For the IncidentBench framing, these are results of exercising and inspecting a connected incident-response workflow. They support the usefulness of exposing stage-specific outcomes and repeated behavior. They do not establish benchmark superiority, detector superiority, production readiness, or agent-caused recovery.

## 2. Dataset, selection, and provenance

### 2.1 Analysis cohort

The three application folders contain 69 archived attempts with 69 matching grade files, representing **67 distinct scenario identities**. Online Boutique contains two superseded failed/interrupted attempts; selecting the latest completed attempt leaves 21 scenario runs. Sock Shop has 23 selected completed runs. TeaStore has 23 selected scenarios, of which two do not meet the notebook helper's completion rule. The primary analysis excludes those two technical run failures, giving **65 completed runs: 21 Online Boutique, 23 Sock Shop, and 21 TeaStore**.

| Application | Archived/graded attempts | Distinct selected scenarios | Completed runs analyzed | Selected technical runs excluded |
| --- | ---: | ---: | ---: | ---: |
| Online Boutique | 23 | 21 | 21 | 0 |
| Sock Shop | 23 | 23 | 23 | 0 |
| TeaStore | 23 | 23 | 21 | 2 |
| Total | 69 | 67 | 65 | 2 |

Six additional historical technical attempts are stored under [`results/failed/`](results/failed/), with no matching application-grade cohort. They are outside this analysis. The two superseded Online Boutique attempts concern cartservice CPU and productcatalogservice CPU; their completed replacements are included. Two configured one-hour Online Boutique scenarios have no corresponding archive in this snapshot: `online-boutique-pod-checkoutservice-capacity-loss-one-hour` and `online-boutique-pod-shippingservice-bandwidth-all-one-hour`. Thus, the configured suite size of 69 must not be reported as 69 completed or distinct evaluated scenarios.

The two excluded selected TeaStore runs are:

- [`teastore-node-memory-worker-3-one-hour`](results/teastore/20260923-161855-teastore-node-memory-worker-3-one-hour-09476bb4/run-status.json): metadata reports `cleanup_failed`, and execution return code is 3.
- [`teastore-pod-webui-cpu-headroom-all-one-hour`](results/teastore/20260924-034047-teastore-pod-webui-cpu-headroom-all-one-hour-844b969f/run-status.json): metadata says `completed`, but `run-status.json` says `failed`. The helper explicitly treats a failed status as overriding completion, even though the recorded execution return code is zero.

These exclusions are based on execution evidence, not scores. Poor diagnoses, unsuitable remediation, no-action decisions, and low scores in completed runs remain included. A failed **job** is also not equivalent to a failed **experiment**: 31 failed-lifecycle Sock Shop remediation jobs have usable final scores, including eight scores above 0.8, and are retained.

The primary cohort differs slightly from the notebook's unfiltered semantic aggregates. By default, the notebook retains semantic evidence from both excluded TeaStore scenarios: RCA becomes 32/187 successful sessions and 15/23 successful scenarios; remediation becomes 11/168 and 9/23. The completed-only figures here are 30/171 and 13/21 for RCA, and 10/153 and 8/21 for remediation. The notebook already excludes these runs from aggregate performance counts, so the performance totals do not change. This is the only deliberate cohort restriction beyond notebook selection.

### 2.2 Experimental and grading conditions

The included runs started between 15 and 24 September 2026, in UTC. Each archived resolved scenario specifies a 30-minute baseline, a 60-second grace setting, and one 60-minute scheduled chaos interval. The notebook discards the first five baseline minutes. All included runs enable agents. The archived constant-load targets are application-specific:

| Application | Base users | Configured additional user bias | Spawn rate | Load-shape seed | Frontend selector |
| --- | ---: | ---: | ---: | ---: | --- |
| Online Boutique | 600 | 0–60 | 10 users/s | 1 | `frontend` |
| Sock Shop | 100 | 0–10 | 10 users/s | 1 | `front-end` |
| TeaStore | 200 | 0–20 | 10 users/s | 1 | `teastore-webui` |

These are configured concurrency targets, not measured request rates or equivalent application load. Each selector is restricted to its application namespace. Comparisons across applications are descriptive contrasts under different workloads and architectures, not a controlled ranking of inherent application difficulty.

All 69 grade configurations record judge model `Qwen/Qwen3.6-35B-A3B`, prompt version `sustained-recovery-grader-v4`, an 8192-token judge limit, and concurrency 5. `model_revision` is unrecorded. The common canonical rubric hash is `5c90dca423498990cd94a651fa60b1a2570478da450116a344cb8ea1bbf91b15`; the policy hash is `131ff6091e58e5f61d3a6c0bb46c1af20c8ed95a7a3c96b44112fd2c9b2eff0d`. Scenario-specific penalty hashes are preserved in each grade. The historical response-model identity/revision is not established by the inspected archive configuration records; current deployment settings should not be substituted for that missing provenance.

Archived anomaly events retain version-1 profile identifiers and effective parameters for threshold and Z-score detection. These records support tracing the initiating signals, but the selected dataset does not establish an experiment comparing detector configurations.

The grade evidence inventory labels semantic grounding as `reported_evidence_quality`, with no supplemental `evidence/` observations in these records. Consequently, the scores primarily judge final reports against LLM-assisted, author-guided expectations and reported evidence. They are not independent validation of every claimed tool action or complete reasoning trajectory. The configured judge and reference policy are part of the measurement process.

### 2.3 Why metrics were recomputed

The maintained [`eda/report.md`](eda/report.md) and this analysis both use offline recomputation of archived telemetry with the correct application selectors and existing semantic grades; neither rejudges the outputs. Historical `paired_window` blocks in some Online Boutique and TeaStore grade files used the legacy `front-end` selector without an application namespace, so their performance values were not used here.

## 3. Metric interpretation

Only the notebook's reported metric families are used: semantic score summaries, session counts, Time to Maximum Score, baseline and paired best frontend windows, their absolute and relative changes, and semantic-success/Window-Tolerance aggregates. The grader's separate operational recovery-proxy branch is outside this report.

| Metric | Interpretation used here |
| --- | --- |
| Maximum/Mean Semantic Score | Maximum/arithmetic mean of usable final scores completed during recorded chaos; 0–1 scale. Remediation scores include penalties. |
| Session Count / Scored Session Count | Exported jobs completed during chaos / those having a usable semantic score. Missing scores are not zero. |
| Semantic Session Success | Score strictly greater than 0.8, divided by scored sessions. A score of exactly 0.8 fails this threshold. |
| Scenario Semantic Success | At least one score above 0.8, divided by scenarios having at least one scored output of that kind. |
| Time to Maximum Score | Earliest completion attaining that run's maximum score, minus recorded chaos start, in minutes. It can refer to a poor or zero-scoring output. |
| Mean Rolling P95 Latency | Time average of the frontend's archived rolling P95 series in seconds, not a pooled client or end-to-end shopping-journey percentile. |
| Mean HTTP 5xx Rate | Time-average response rate in requests/s, not an error fraction. |
| Best window | Covered five-minute window with minimum mean rolling P95 among candidates with mean 5xx ≤0.5 requests/s. |
| Window Tolerance | Window P95 <1.2 × baseline P95 **and** mean 5xx ≤0.5 requests/s. This permits latency degradation below 20%. |

Eligibility uses completion timestamps within `[active chaos start, min(cleanup start, active start + configured duration))`. The end is exclusive. Reports before/after that interval or without completion times are excluded from scores, timing, and Session Count. A scheduled interval may contain recurring fault pulses; inclusion does not prove continuous child-fault activity.

Performance windows remain inside recorded chaos and the telemetry collection deadline. The integration requires at least two samples and 90% coverage; selected windows in this cohort have at least 95.0% coverage for both reported series. Latency and 5xx always come from the same selected window. Absolute change is window minus baseline; percentage change is defined only for a positive baseline. If all covered windows violate the error ceiling, the grader marks the paired measurement `not_evaluable` and leaves the best measurements unavailable. With a valid positive baseline, the EDA still counts Best-Window Tolerance as a **known failure**; an unavailable baseline leaves that flag unknown.

The run/scenario is the experimental unit. Pooled session fractions describe the collection of outputs and give greater weight to runs producing more sessions. They are not estimates from hundreds of independent experiments. Equal-weight averages of scenario scores are explicitly distinguished below.

## 4. Semantic assessment and response behavior

### 4.1 Attainment is substantially higher than consistency

| Application | RCA session success | RCA scenario success | Remediation session success | Remediation scenario success |
| --- | --- | --- | --- | --- |
| Online Boutique | 48/163 (29.4%) | 15/21 (71.4%) | 10/95 (10.5%) | 9/20 (45.0%) |
| Sock Shop | 41/169 (24.3%) | 18/22 (81.8%) | 19/103 (18.4%) | 10/19 (52.6%) |
| TeaStore | 30/171 (17.5%) | 13/21 (61.9%) | 10/153 (6.5%) | 8/21 (38.1%) |
| Pooled descriptive total | 119/503 (23.7%) | 46/64 (71.9%) | 39/351 (11.1%) | 27/60 (45.0%) |

Unknown scenario scores: one RCA and five remediation across the 65 runs. These are excluded from the relevant semantic denominators, not counted as unsuccessful scores.

RCA exceeds remediation in both session and scenario success for every application. This supports describing a diagnosis-to-action gap in the assessed reports. It does not mean that every successful RCA was followed by an unsuccessful remediation in the same workflow: these are separate run-level maxima, and matched-workflow examples are examined below.

Across the completed cohort, 24 runs attain successful outputs of both kinds. Three successful-remediation runs never attain a successful RCA score. A downstream report can therefore receive a favorable assessment even when no preceding run-level RCA output exceeds the threshold. Conversely, a strong RCA maximum does not imply consistent diagnosis throughout the run.

| Application | Output kind | Mean of scenario maxima | Mean of scenario means | Pooled session mean |
| --- | --- | --- | --- | --- |
| Online Boutique | RCA | 0.841 | 0.482 | 0.460 |
| Online Boutique | Remediation | 0.609 | 0.308 | 0.335 |
| Sock Shop | RCA | 0.841 | 0.458 | 0.456 |
| Sock Shop | Remediation | 0.749 | 0.417 | 0.338 |
| TeaStore | RCA | 0.738 | 0.364 | 0.369 |
| TeaStore | Remediation | 0.589 | 0.207 | 0.205 |

The first two score columns give each semantically evaluable scenario equal weight; the final column gives each scored output equal weight.

The mean of scenario maxima is much higher than the mean of scenario-average scores. For example, Online Boutique's RCA values are 0.841 versus 0.482; its remediation values are 0.609 versus 0.308. The same pattern holds for the other applications. Selecting only each run's best output would conceal substantial partial, incorrect, or poorly supported reporting.

Sock Shop has the highest remediation scenario success in this cohort, but only 19/103 scored remediation sessions exceed the threshold. TeaStore produces many remediation outputs while attaining the lowest session success, 10/153. Neither result supports a general model ranking: workload, scenario targets, preceding actions, and response configuration are not controlled across applications.

### 4.2 Sessions and Time to Maximum Score

| Application | Output kind | Sessions/scored | Sessions per run: median (range) | Time to maximum: median [Q1, Q3], min | Timing range, min |
| --- | --- | --- | --- | --- | --- |
| Online Boutique | RCA | 163/163 | 7 (4–14) | 13.36 [9.31, 18.76] | 5.80–39.27 |
| Online Boutique | Remediation | 107/95 | 4 (0–9) | 17.40 [13.64, 27.39] | 5.12–58.43 |
| Sock Shop | RCA | 169/169 | 8 (0–15) | 13.86 [7.27, 25.08] | 4.46–54.88 |
| Sock Shop | Remediation | 110/103 | 5 (0–9) | 15.32 [10.49, 33.06] | 3.76–59.06 |
| TeaStore | RCA | 171/171 | 8 (4–10) | 21.79 [8.45, 34.61] | 6.85–53.42 |
| TeaStore | Remediation | 160/153 | 8 (4–9) | 22.70 [10.46, 34.85] | 3.28–58.38 |

Session medians include zero-output runs. Timing statistics include only the 64 RCA-evaluable and 60 remediation-evaluable runs; all of their maximum-score completion times are available.

There are 503 in-scope RCA completions, all scored, and 377 remediation completions, of which 351 are scored. The 26 unscored remediation completions have no final result; none represents a failed judge call in this cohort. These records remain in Session Count but not score averages or semantic-success denominators. The analysis does not investigate their technical causes.

The completed-run archives contain 623 exported RCA and 446 exported remediation jobs. The chaos filter excludes 120 RCA jobs (94 outside the interval, 26 missing valid completion timestamps) and 69 remediation jobs (58 outside, 11 missing valid completion timestamps). Thus, Session Count here means completed outputs within the evaluation boundary, not every submitted investigation or all activity during a run.

Five scenarios have no in-scope scored remediation: Sock Shop node memory, carts CPU, catalogue bandwidth, shipping bandwidth, and Online Boutique productcatalogservice bandwidth. Sock Shop node memory also has no in-scope RCA. Its archives contain two RCA and two remediation jobs, but none completes within the reporting interval. It should not be described as having no response activity at all, nor as a measured detector miss.

TeaStore's median Time to Maximum Score is later than the other applications, but this is a retrospective quality-timing description, not a measured detection or recovery delay. It combines initiation, dispatch, investigation, repeated work, and completion. In TeaStore recommender bandwidth, the remediation maximum is zero and is reached after only 3.28 minutes. That short time plainly does not indicate effective response. RCA and remediation timing summaries also refer to different job sets; subtracting their medians would not estimate remediation duration.

Repeated outputs create opportunities to obtain a high maximum, but do not establish progressive learning or improvement. In Online Boutique node-delay worker-3, three early RCA outputs score 1.0, followed by eight scored outputs between zero and 0.275. In Sock Shop carts CPU, 15 RCA outputs yield only one score above 0.8 and no remediation. These trajectories warrant discussion alongside maxima and timing.

## 5. Performance comparison

### 5.1 Favorable windows and their interpretation

| Application | Best-Window Tolerance | Median best P95 change |
| --- | --- | ---: |
| Online Boutique | 12/21 (57.1%) | 1.0% |
| Sock Shop | 21/23 (91.3%) | -0.8% |
| TeaStore | 11/21 (52.4%) | 2.5% |
| Pooled descriptive total | 44/65 (67.7%) | -0.6% |

Best-window latency-change medians use the 62 runs with a selected best window (20 Online Boutique, 22 Sock Shop, 20 TeaStore). The three error-rejected runs still count as failures in the 65-run tolerance denominator.

Best-Window Tolerance reports the existence of a favorable selected period under the error ceiling, rather than sustained satisfactory service. Passing this flag does not prove that every other chaos window satisfies the latency or 5xx threshold.

Sock Shop's 21/23 best-window passes coexist with weak or absent semantic responses in several scenarios. Online Boutique has 12/21 best-window passes, and TeaStore has 11/21. These favorable periods do not establish absence of a local fault or sustained service quality.

These latency values are time averages of rolling P95, not request-level percentile recomputations. An application-level median can also conceal severe individual cases.

Not every best window is near baseline. TeaStore image bandwidth has baseline P95 0.0545 s and best-window P95 4.3428 s (+7,869.9%), even though its selected best-window 5xx rate is zero. This demonstrates a performance incident in which the frontend can avoid reported 5xx responses while becoming much slower.

### 5.2 Error-constrained best windows and imputation

Three completed runs have no best window satisfying the error ceiling. They remain in the denominator as known Best-Window Tolerance failures:

| Application/scenario | Baseline P95 (s) | Baseline 5xx (requests/s) |
| --- | ---: | ---: |
| Online Boutique: paymentservice capacity loss | 0.1043 | 0.0290 |
| Sock Shop: payment capacity loss | 0.0940 | 0.0000 |
| TeaStore: registry capacity loss | 0.0475 | 0.0000 |

All covered five-minute candidates fail the mean-5xx ceiling in these runs. This is a consequential service outcome, not a missing-data or operational-run exclusion.

The helper imputes absent 5xx samples as zero only at matching traffic timestamps when the archived error query successfully returns a matrix. Positive imputation counts occur in nine Sock Shop baselines, eight Sock Shop best windows, and one TeaStore best window; none occurs in Online Boutique. Each affected selected five-minute window has 20 imputed samples. Nine of the 44 passing best windows therefore rely on this documented convention for at least some error evidence. Latency is not imputed.

Baseline 5xx is zero in 21 Sock Shop and 20 TeaStore runs. Their relative 5xx changes are undefined, including when both baseline and selected window are zero. The detailed tables retain absolute differences and mark percentage changes unavailable. A low absolute 5xx rate must also not be equated with a low error fraction: slower or reduced traffic can lower errors per second.

### 5.3 Semantic success and Window Tolerance are related observations, not substitutes

Among the 60 scenarios with scored remediation, the descriptive cross-tabulation is:

| Remediation scenario outcome | Best window passes | Best window fails | Total |
| --- | ---: | ---: | ---: |
| At least one score >0.8 | 19 | 8 | 27 |
| Scored outputs, none >0.8 | 20 | 13 | 33 |
| Total evaluable for both | 39 | 21 | 60 |

The remaining five runs have no scored remediation and all pass Best-Window Tolerance. Thus, satisfactory selected frontend windows occur both with and without successful remediation assessments. Conversely, eight runs attain a high remediation score while failing Best-Window Tolerance. The corresponding RCA cross-tabulation has 31 passing and 15 failing best windows among 46 RCA-success scenarios, versus 12 passing and six failing among 18 scored RCA-nonsuccess scenarios.

These small, heterogeneous groups provide no controlled causal estimate. The best window can occur before or after a particular action, and recurring fault timing, workload behavior, native controllers, and earlier interventions can all affect it. The two assessment paths reveal different properties of the same run; neither should be relabeled as verified recovery.

## 6. Scenario-family analysis

The following groups are derived from archived scenario names. Counts retain the notebook's evaluable denominators. They are descriptive strata, not additional benchmark metrics or balanced treatments.

| Family | Runs | RCA scenario success | Remediation scenario success | Best tolerance |
| --- | --- | --- | --- | --- |
| Node CPU | 3 | 2/3 | 1/3 | 3/3 |
| Node delay | 9 | 9/9 | 7/9 | 9/9 |
| Node packet loss | 9 | 4/9 | 2/9 | 2/9 |
| Node memory | 2 | 0/1 | 1/1 | 2/2 |
| Pod CPU headroom | 8 | 6/8 | 1/8 | 6/8 |
| Pod bandwidth | 5 | 0/5 | 0/2 | 4/5 |
| Pod capacity loss | 5 | 5/5 | 1/5 | 2/5 |
| Pod CPU | 15 | 13/15 | 9/14 | 8/15 |
| Pod memory | 9 | 7/9 | 5/9 | 8/9 |

Node delay has 9/9 successful RCA, 7/9 successful remediation, and 9/9 favorable best windows. Node packet loss is much less favorable, particularly in TeaStore, where none of the three packet-loss scenarios attains either semantic success or Best-Window Tolerance. These differences concern the specific tested scenarios and placements.

Bandwidth restriction is the weakest RCA family: maximum RCA scores range from 0 to 0.275. Two TeaStore cases produce remediation outputs, but neither attains success; the three other bandwidth cases have no in-scope remediation completion. Four favorable best windows coexist with this poor semantic performance. The TeaStore image-bandwidth exception is severe even in its best window, whereas TeaStore recommender bandwidth is within tolerance in its best window despite nine zero-scoring remediation outputs. A single frontend summary does not expose every target-specific failure mode.

CPU-headroom scenarios show a large diagnosis-to-remediation drop: 6/8 attain successful RCA, only 1/8 successful remediation. The case evidence includes resource increases that conflict with schedulability or scenario-specific CPU-headroom criteria. Recurring capacity-loss scenarios show a similar pattern: all five attain successful RCA, but only one successful remediation, and only two acceptable best windows. It is useful to separate identifying lost capacity from producing a durable, policy-consistent intervention.

Memory scenarios often have favorable best windows, including when diagnosis is weak. This does not establish that memory incidents are easy: TeaStore auth-memory remains 63.7% above baseline even in its best window, while the Online Boutique currencyservice case receives a perfect remediation score without usable reported post-action symptom measurements.

### 6.1 Cross-application comparison within fault families

**Application differences persist within the same fault family, and the archives point to differences in starting configuration, fault exposure, workload paths, initiating evidence, and subsequent response.** The application-level totals alone cannot separate these factors. The table below compares the same reported outcomes within each family. `R` and `M` are Scenario Semantic Success for RCA and remediation; `B` is Best-Window Tolerance. Every fraction is successful/evaluable, not successful/all configured scenarios. An em dash means no evaluable scenario of that kind; it is not zero performance.

| Family | Application | Runs | R | M | B |
| --- | --- | ---: | --- | --- | --- |
| Node CPU | Online Boutique | 1 | 1/1 | 0/1 | 1/1 |
| Node CPU | Sock Shop | 1 | 1/1 | 1/1 | 1/1 |
| Node CPU | TeaStore | 1 | 0/1 | 0/1 | 1/1 |
| Node delay | Online Boutique | 3 | 3/3 | 2/3 | 3/3 |
| Node delay | Sock Shop | 3 | 3/3 | 2/3 | 3/3 |
| Node delay | TeaStore | 3 | 3/3 | 3/3 | 3/3 |
| Node packet loss | Online Boutique | 3 | 2/3 | 1/3 | 0/3 |
| Node packet loss | Sock Shop | 3 | 2/3 | 1/3 | 2/3 |
| Node packet loss | TeaStore | 3 | 0/3 | 0/3 | 0/3 |
| Node memory | Online Boutique | 1 | 0/1 | 1/1 | 1/1 |
| Node memory | Sock Shop | 1 | — | — | 1/1 |
| Node memory | TeaStore | 0 | — | — | — |
| Pod CPU | Online Boutique | 5 | 5/5 | 4/5 | 1/5 |
| Pod CPU | Sock Shop | 5 | 4/5 | 3/4 | 5/5 |
| Pod CPU | TeaStore | 5 | 4/5 | 2/5 | 2/5 |
| Pod CPU headroom | Online Boutique | 3 | 2/3 | 0/3 | 2/3 |
| Pod CPU headroom | Sock Shop | 3 | 3/3 | 1/3 | 3/3 |
| Pod CPU headroom | TeaStore | 2 | 1/2 | 0/2 | 1/2 |
| Pod bandwidth | Online Boutique | 1 | 0/1 | — | 1/1 |
| Pod bandwidth | Sock Shop | 2 | 0/2 | — | 2/2 |
| Pod bandwidth | TeaStore | 2 | 0/2 | 0/2 | 1/2 |
| Pod capacity loss | Online Boutique | 1 | 1/1 | 0/1 | 0/1 |
| Pod capacity loss | Sock Shop | 2 | 2/2 | 0/2 | 1/2 |
| Pod capacity loss | TeaStore | 2 | 2/2 | 1/2 | 1/2 |
| Pod memory | Online Boutique | 3 | 1/3 | 1/3 | 3/3 |
| Pod memory | Sock Shop | 3 | 3/3 | 2/3 | 3/3 |
| Pod memory | TeaStore | 3 | 3/3 | 2/3 | 2/3 |

The regular pod-CPU family is particularly useful because each application contributes five scenarios. Online Boutique attains successful RCA in 5/5 and remediation in 4/5, compared with Sock Shop's 4/5 and 3/4 evaluable cases. Yet only 1/5 Online Boutique runs passes Best-Window Tolerance, versus 5/5 Sock Shop and 2/5 TeaStore. Thus, Sock Shop's favorable service-window results cannot be explained simply by better diagnosis or remediation grades. Equally, Online Boutique's stronger CPU diagnosis attainment does not imply better frontend behavior.

Other families are less balanced: Online Boutique contributes only one bandwidth and one capacity-loss scenario; TeaStore has no included node-memory run and only two CPU-headroom runs. Targets also differ within families. For example, TeaStore's two bandwidth cases have best P95 changes of +1.3% and +7,869.9%; their midpoint is not a meaningful description of a typical TeaStore bandwidth incident. The case comparisons below retain the actual targets and absolute latencies.

### 6.2 Why the same injected setting is not the same application exposure

The archived workload implementations establish different demand paths. Online Boutique independently samples weighted tasks: product browsing has weight 10 and checkout weight 1, with other weights for currency, cart, and index operations. Sock Shop executes an ordered shopping task containing catalogue, customer/login, cart, and order requests, with a 1–5 second configured wait between tasks. TeaStore executes login, one to three browsing iterations, cart, checkout, profile, and logout, including waits inside the journey and a 1–10 second configured wait range. Sock Shop and TeaStore abort the remaining task after a failed checked request; TeaStore additionally checks response text for successful login/cart/checkout outcomes. These scripts are byte-identical within each application's completed cohort. Sources: archived [Online Boutique workload](results/online-boutique/20260917-135646-online-boutique-node-delay-worker-2-one-hour-e5daaf4c/inputs/source/testbed/loadgenerator/common.py), [Sock Shop workload](results/sock-shop/20260915-085323-sock-shop-node-delay-worker-2-one-hour-6d3be870/inputs/source/resources/applications/sock_shop.py), and [TeaStore workload](results/teastore/20260921-214910-teastore-node-delay-worker-2-one-hour-b007dcff/inputs/source/resources/applications/teastore.py).

These are concrete reasons that an affected service need not contribute equally to the frontend metric across applications. A failure early in a sequential journey can prevent later requests; an independently sampled browse task does not require completing a checkout journey first. Different wait patterns and configured user counts also mean different offered demand relative to provisioned capacity. The archives establish these workload differences, but this analysis does not quantify how much each accounts for a particular latency gap. In particular, a TeaStore workload semantic failure can be recorded by Locust even when the final HTTP response is 200; the notebook's frontend 5xx metric does not measure that same condition.

Runtime placement is another direct difference. For the matched **worker-2 network-delay** runs, the `before-chaos` pod snapshots were taken approximately 29–34 seconds before fault activation. They show the following ready replicas on the target node; fractions are target-node replicas / application-wide replicas of that deployment at that snapshot:

| Application | Ready deployment replicas on worker 2 immediately before chaos | Relevant operational distinction |
| --- | --- | --- |
| Online Boutique | checkoutservice 1/2; emailservice 1/2; frontend 2/9; productcatalogservice 1/4; shippingservice 1/2 | Several replicated services and frontend replicas share the affected node. |
| Sock Shop | front-end 1/6; orders 1/2; user-db 1/1 | The affected node also contains the only user-db replica, with local `emptyDir` storage. |
| TeaStore | teastore-persistence 1/3; teastore-webui 1/6 | The affected deployment mixture differs from both other applications. |

Sources: [Online Boutique pre-chaos pods](results/online-boutique/20260917-135646-online-boutique-node-delay-worker-2-one-hour-e5daaf4c/snapshots/before-chaos/pods-json.out), [Sock Shop pre-chaos pods](results/sock-shop/20260915-085323-sock-shop-node-delay-worker-2-one-hour-6d3be870/snapshots/before-chaos/pods-json.out), and [TeaStore pre-chaos pods](results/teastore/20260921-214910-teastore-node-delay-worker-2-one-hour-b007dcff/snapshots/before-chaos/pods-json.out). Sock Shop's storage configuration is also recorded in its [deployment snapshot](results/sock-shop/20260915-085323-sock-shop-node-delay-worker-2-one-hour-6d3be870/snapshots/before-chaos/deployments-json.out).

These observations should take precedence over assuming that a placement preset fixes every pod present at fault activation. For example, Online Boutique's frontend grows from six replicas before load to nine in this pre-chaos snapshot. The archived HPA and pod snapshots show that the operating state can change during baseline. Consequently, the same worker identifier or fault parameter does not establish an identical set or fraction of affected dependencies. This explains a difference in experimental exposure; it does not, by itself, prove the cause of every observed outcome.

### 6.3 Node faults: a shared delay pattern, but different diagnosis and action constraints

The matched worker-2 delay manifests use the same configured 250 ms delay, 50 ms jitter, correlation 25, and 25-second child duration on a 30-second schedule, including complementary directional rules. The packet-loss manifests use 20% loss with correlation 25 and the same pulse timing. Node-CPU worker-2 uses eight stress workers at 90%, also for 25 seconds every 30 seconds. These comparisons hold the configured injection setting constant; they do not normalize service demand or fault-time placement. The archived definitions are available in the matched runs' `inputs/chaos/` folders.

| Matched worker-2 fault | Online Boutique: RCA max / remediation max; best L | Sock Shop: RCA max / remediation max; best L | TeaStore: RCA max / remediation max; best L |
| --- | --- | --- | --- |
| Delay | 1.0000 / 1.0000; 0.0974 s | 1.0000 / 0.6750; 0.0786 s | 1.0000 / 1.0000; 0.0544 s |
| Packet loss | 0.5000 / 0.5250; 0.3854 s | 0.9375 / 0.7500; 0.1000 s | 0.2750 / 0.4000; 0.4423 s |
| CPU pressure | 1.0000 / 0.6875; 0.0936 s | 1.0000 / 0.9625; 0.0696 s | 0.4250 / 0.2875; 0.0505 s |

**What is similar:** node delay is the most consistent cross-application pattern. All nine delay scenarios attain successful RCA and a passing best window. Their shared scheduled disturbance is compatible with a recurring-fault explanation, but the selected best windows are not synchronized to individual pulses here. TeaStore can therefore be diagnosed well in this family. It would be inaccurate to interpret its weaker overall semantic totals as uniformly weak node diagnosis.

**Why remediation differs even with the same diagnosis:** in Sock Shop worker-2 delay, the maximum remediation is 0.675, compared with 1.0 in the matched Online Boutique and TeaStore runs. The affected Sock Shop node contains the only user-db replica. The report describes evacuation, while the judge identifies incomplete data-preserving handling of that database's local storage. This is a concrete application-specific action constraint, rather than merely a difference in whether the bad node was found. The archived [Sock Shop grade](grades/sock-shop/runs/20260915-085323-sock-shop-node-delay-worker-2-one-hour-6d3be870/grade.json) supports that explanation of the grading difference; it does not independently establish that data were lost.

**Why packet loss should be discussed separately:** Sock Shop worker-2 has a favorable best period (+5.4% P95), but Online Boutique and TeaStore remain +265.8% and +774.4% above baseline in their best periods. TeaStore's low node-loss scores and reports focused on application/configuration symptoms differ from its strong node-delay localization. The joint evidence is consistent with fault-dependent symptom propagation and investigation focus, not a single application-wide agent capability. The current data do not isolate how much of the latency difference comes from network sensitivity, application retries, controller behavior, or the interventions themselves.

The CPU-pressure row reinforces the distinction: the same node stress configuration has passing best windows in Sock Shop and TeaStore, while the report trajectories differ. Sock Shop identifies host-level CPU consumption and reports node isolation; Online Boutique identifies node saturation but reports redistributing application deployments without completing node isolation; TeaStore prioritizes webui retries and persistence symptoms and reports a persistence restart. These different scopes explain part of the semantic-grade contrast. Sources: [Sock Shop node-CPU grade](grades/sock-shop/runs/20260916-044232-sock-shop-node-cpu-worker-2-one-hour-e7fb3d20/grade.json), [Online Boutique node-CPU grade](grades/online-boutique/runs/20260918-075737-online-boutique-node-cpu-worker-2-one-hour-842bd119/grade.json), and [TeaStore node-CPU grade](grades/teastore/runs/20260922-155606-teastore-node-cpu-worker-2-one-hour-5f003308/grade.json).

Those response differences do not establish which action caused a frontend change. Sock Shop's selected best window starts 54.25 minutes after chaos begins and overlaps completion of its maximum-scoring remediation at 56.76 minutes; it is not a window wholly after that report. Different fault-time occupants and capacity-to-demand conditions are additional supported reasons to avoid treating the injections as equal service-level stress. A claim that TeaStore's implementation language or runtime alone explains the gap is not established by these runs.

### 6.4 Bandwidth: shared diagnostic weakness, different frontend consequences

The compared catalogue/image bandwidth schedules cap all selected running target pods at 1 Mbps, with buffer 10000, limit 2097152, and a 25-second duration every 30 seconds. The target and application path nevertheless differ. The resulting contrasts are unusually clear:

| Application and target | RCA max; RCA/remediation Session Count | Baseline L | Best L | Best tolerance |
| --- | --- | ---: | ---: | --- |
| Online Boutique productcatalogservice | 0.2375; 14/0 | 0.1089 s | 0.1039 s | Yes |
| Sock Shop catalogue | 0.1125; 3/0 | 0.0937 s | 0.0931 s | Yes |
| Sock Shop shipping | 0.0000; 1/0 | 0.0929 s | 0.0917 s | Yes |
| TeaStore image | 0.2375; 10/9 | 0.0545 s | 4.3428 s | No |
| TeaStore recommender | 0.2750; 9/9 | 0.0471 s | 0.0477 s | Yes |

The commonality is poor localization of the expected throughput restriction: no RCA exceeds 0.8, despite different amounts of response activity. The difference is what happens to the frontend and whether remediation proceeds. TeaStore image is severely degraded even in the best window, whereas Sock Shop's two cases have best windows within tolerance. TeaStore recommender also differs greatly from TeaStore image, so the explanation cannot be only the application name or its user count. Target role, demand per affected replica, payload and caching behavior, and the observed response are candidate mechanisms; the present frontend summaries do not individually quantify these mechanisms. In particular, the available evidence does not justify declaring that larger image payloads alone caused the TeaStore image result.

There is direct evidence that these investigations also begin from different leads. The **earliest completed in-scope RCA** in Sock Shop catalogue receives a worker-4 node-network-I/O anomaly (`06d38412-3ae1-4a66-aee8-9d820910f8d9`); Online Boutique catalog receives a currencyservice CPU-request-utilization anomaly (`4c3f0a8b-07b6-4d1d-a972-ad7c3a004955`); TeaStore image receives auth and recommender memory-request-utilization anomalies (`45d0c894-e0ee-48da-acc6-b4ae42b12101`). These are archived RCA requests, not inferred labels: [Sock Shop request export](results/sock-shop/20260916-120946-sock-shop-pod-catalogue-bandwidth-all-one-hour-5602bb98/sessions/rca_session.json), [Online Boutique request export](results/online-boutique/20260921-052319-online-boutique-pod-productcatalogservice-bandwidth-all-one-hour-b7a779ab/sessions/rca_session.json), and [TeaStore request export](results/teastore/20260923-180616-teastore-pod-image-bandwidth-all-one-hour-b6362ec3/sessions/rca_session.json).

Those examples explain why a common injected fault family does not present a common investigation prompt. They support examining the detection-to-investigation boundary: the response must connect indirect initiating symptoms to the affected target. They do not prove that a detector missed the bandwidth fault, that these were the first jobs launched, or that a different detector would improve diagnosis. Later reports and actions remain part of the explanation, including the repeated off-target TeaStore interventions discussed in Section 7.5.

### 6.5 CPU headroom: baseline configuration changes the meaning of improvement

The headroom scenarios change the resource context before the fault. Archived manifests set CPU request equal to limit across [all eleven Online Boutique deployments](results/online-boutique/20260921-161532-online-boutique-pod-productcatalogservice-cpu-headroom-all-one-hour-364220b4/application-rendered.yaml) and [all seven TeaStore deployments](results/teastore/20260924-081400-teastore-pod-image-cpu-headroom-all-one-hour-dc9c3753/application-rendered.yaml) in these profiles. Sock Shop's headroom profile constrains three deployments together: front-end to 100m/100m, catalogue to 100m/100m, and orders to 200m/200m. In the ordinary Sock Shop profile, those pairs are 400m/800m, 100m/200m, and 250m/750m. Therefore, a headroom run is not an ordinary CPU run with only a different fault label or only one target's resource setting changed. Sources include the archived [Sock Shop ordinary baseline deployments](results/sock-shop/20260915-235020-sock-shop-pod-catalogue-cpu-all-one-hour-72f06623/snapshots/baseline-before-load/deployments-json.out) and [headroom baseline deployments](results/sock-shop/20260917-085658-sock-shop-pod-catalogue-cpu-headroom-all-one-hour-a4bb7faa/snapshots/baseline-before-load/deployments-json.out), alongside the corresponding application manifests and snapshots for the other applications.

| Within-application target | Ordinary CPU baseline L | Headroom baseline L | Ordinary CPU best L | Headroom best L |
| --- | ---: | ---: | ---: | ---: |
| Sock Shop catalogue | 0.0950 s | 0.4451 s | 0.0979 s | 0.1224 s |
| Online Boutique productcatalogservice | 0.0979 s | 0.1087 s | 0.1741 s | 0.2268 s |
| TeaStore image | 0.0868 s | 0.1911 s | 0.0901 s | 0.1418 s |

Sock Shop illustrates the interpretive issue particularly well. Catalogue ordinary CPU has a best-window change of **+3.0%**, while catalogue headroom has **−72.5%**. Nevertheless, the headroom best window is slower in absolute terms: 0.1224 s versus 0.0979 s. The larger relative reduction starts from a much slower reference. Window Tolerance combines a run-specific relative latency bound and an absolute error ceiling; it is not an ordering of absolute application performance.

This explains an important part of why Sock Shop's headroom outcomes look favorable in the aggregate without establishing stronger agent remediation. Three Sock Shop headroom runs pass best-window tolerance, but only one attains remediation semantic success. In Online Boutique, the checkout interventions receive large policy deductions despite reported CPU increases, while catalog actions report Pending pods after oversized requests. TeaStore headroom runs also have changed starting configurations and large latency excursions. These response and policy differences are evidenced in grades; their causal contribution to the frontend trajectories remains unseparated from the resource configuration and workload.

Even the nominal stress severity varies across headroom targets: requests/limits differ, and stress load is target-specific. The analysis should therefore report the actual starting resources and baseline with each comparison, rather than treating a shared CPU-headroom label as an equal dose of pressure.

### 6.6 Capacity loss and memory: shared symptoms do not imply the same correct action

Recurring capacity loss has a common service symptom in three otherwise different targets: Online Boutique paymentservice, Sock Shop payment, and TeaStore registry have no covered five-minute window meeting the error ceiling. Their schedules all use a one-pod failure with a 25-second child duration every 30 seconds. All three attain successful RCA, but remediation maxima are 0.725, 0.450, and 1.000 respectively. The TeaStore registry report receives full credit for restoring its singleton rather than adding replicas/HPA, while the payment scenarios are judged against their own durable-capacity expectations. The high TeaStore score does not erase its missing error-qualified best window. This is a similarity in user-visible error behavior coupled with a difference in the acceptable intervention and its assessment. The [registry grade](grades/teastore/runs/20260924-014522-teastore-pod-registry-capacity-loss-one-hour-23799335/grade.json), including remediation `dc1c184b-1972-4e42-9dd4-decd046d188a`, records that distinction.

Memory scenarios also vary in the resources and replication semantics of the affected target. Sock Shop carts-db has one replica and local `emptyDir` data storage; TeaStore db has one replica and no HPA in its baseline snapshot. Online Boutique redis-cart, however, is actually deployed with two replicas and a CPU HPA bounded from two to thirty in its archived baseline. It must not be described as execution-equivalent to the two singleton database targets. Sources: [Sock Shop carts-db baseline](results/sock-shop/20260916-140121-sock-shop-pod-carts-db-memory-all-one-hour-d1b6af93/snapshots/baseline-before-load/deployments-json.out), [TeaStore db baseline](results/teastore/20260923-200154-teastore-pod-db-memory-all-one-hour-e44b47ed/snapshots/baseline-before-load/deployments-json.out), and Online Boutique [redis-cart baseline](results/online-boutique/20260921-071113-online-boutique-pod-redis-cart-memory-all-one-hour-add707a0/snapshots/baseline-before-load/deployments-json.out) and [HPA snapshot](results/online-boutique/20260921-071113-online-boutique-pod-redis-cart-memory-all-one-hour-add707a0/snapshots/baseline-before-load/hpa.out).

The configured memory stress is also not a normalized dose. For these database/cache targets, the archived allocation and initial resource budgets are:

| Target | Configured injected allocation | Initial memory request / limit | RCA max / remediation max |
| --- | --- | --- | --- |
| Sock Shop carts-db | 750MB | 256Mi / 768Mi | 1.0000 / 0.5875 |
| Online Boutique redis-cart | 400MB | 256Mi / 512Mi | 0.8125 / 0.0875 |
| TeaStore db | 400MB | 512Mi / 1Gi | 1.0000 / 0.3000 |

These manifest values are configured allocations, not measurements of realized pressure or unused headroom; the applications' existing working sets also matter. All three pass Best-Window Tolerance while their remediation scores remain low. The grade reasons differ: Sock Shop carts-db lacks an established data-preserving path before pod replacement, Online Boutique redis-cart includes other-workload changes and scaling, and TeaStore db changes the request without the limit while also changing recommender. These are different corrective problems under a shared memory label, and different reasons for receiving partial or poor credit.

The embedded [redis-cart grade reference](grades/online-boutique/runs/20260921-071113-online-boutique-pod-redis-cart-memory-all-one-hour-add707a0/grade.json) describes a stateful singleton even though that archived deployment has two replicas and an HPA. This is a reference/execution mismatch that limits interpreting differences in its corrective grades as pure agent capability. It does not independently validate horizontal replication for Redis or authorize reinterpreting the existing scores. More generally, memory pressure on an application service, a cache, and a database carries different data-preservation and replication constraints. The application-family table mixes these targets; it is not a matched comparison of one universal memory remedy.

### 6.7 What the application differences mean for IncidentBench

The evidence supports a layered explanation rather than an inherent ranking of applications:

| Explanatory factor | Evidence established in this snapshot | Conclusion supported |
| --- | --- | --- |
| Workload and request paths | Different archived task sequences, weights, waits, checks, and user targets | Equal fault labels need not affect the same fraction or type of frontend requests. |
| Runtime fault exposure | Different pre-chaos node occupants and replica fractions, including a singleton database in one matched delay case | The same node injection affects different deployment mixtures and intervention constraints. |
| Starting resources and normalization | Different resource profiles and baselines; Sock Shop headroom has large relative reductions from a slower baseline | Percentage improvements and Window Tolerance must be read with absolute latency and errors. |
| Initiating evidence and response trajectory | Different anomaly leads; no-remediation decisions in some runs and repeated off-target action in others | A common injected condition does not give the response system an identical investigation or action sequence. |
| Scenario expectations | Different valid remedies and some reference/execution mismatches | Semantic score differences are conditional on the target-specific assessment policy as well as the reports. |

Under these archived conditions, Sock Shop often retains favorable selected frontend windows, including runs with weak or absent corrective outputs. TeaStore has more remediation sessions, but its node-delay diagnosis is consistently strong. Online Boutique attains strong ordinary-CPU semantic outputs more often than either comparison application, yet most of those CPU scenarios fail Best-Window Tolerance. These are three distinct patterns, not a single continuum from an easy application to a difficult one.

For the paper and thesis, the defensible interpretation is that **the same fault family produces different incident trajectories because it is embedded in a different application, workload, deployment state, and response context**. The archives verify several of those differences directly and provide plausible mechanisms for the outcome contrasts. Estimating how much each factor causes would require matched repetitions or controlled changes to workload, placement, resource profiles, or response configuration. The current contribution is the ability to expose and compare these contexts together with their resulting semantic and service-window outcomes.

## 7. Representative response trajectories

These are purposively selected explanatory cases, not a separately labeled behavioral dataset. Scores and judge reasons come from the linked grades; action details are paraphrases of final reports checked against archived session outputs. Reported actions and readiness are not independently revalidated here. Each linked run has the corresponding `sessions/rca_session.json` and `sessions/remediation_run.json` under `results/<application>/<run>/`.

### 7.1 Repeated investigation can conclude without remediation

In [Online Boutique productcatalogservice bandwidth](grades/online-boutique/runs/20260921-052319-online-boutique-pod-productcatalogservice-bandwidth-all-one-hour-b7a779ab/grade.json), all 14 eligible RCA reports set `remediation_required=false`; 11 still label the incident active. Maximum RCA is 0.2375 (job `b05bcc63-6b98-4ccf-9147-9e8412ae0e3e`), and the grade criticizes missing the catalog throughput restriction while treating CPU utilization and latency symptoms as benign or transient. No remediation output occurs in scope. Best-window P95 is 4.6% below baseline and passes tolerance, which does not establish sustained service quality.

In [Sock Shop carts CPU](grades/sock-shop/runs/20260915-181504-sock-shop-pod-carts-cpu-all-one-hour-d9ce8582/grade.json), all 15 eligible RCA outputs also decline remediation; 12 label the incident recovered and three active. RCA maximum is 0.8625, but mean is 0.4433 and only one output exceeds 0.8. The best window passes tolerance. These are observed response decisions, not evidence that an investigation was never triggered. They illustrate why the benchmark should retain detection, repeated investigations, and no-action decisions rather than reducing each scenario to an isolated best diagnosis.

### 7.2 Relevant diagnosis can lead to controller and scheduling problems

In [Online Boutique recommendationservice CPU](grades/online-boutique/runs/20260918-005141-online-boutique-pod-recommendationservice-cpu-all-one-hour-ea84314b/grade.json), RCA job `ca767b7e-85d9-4f85-b082-1b3744cc0149` scores 1.0. Its matched remediation, `350f6edf-2bec-485a-a3ba-c8730afba6c6`, scores 0.1125 after penalties. The report describes setting 20 replicas while lowering the HPA CPU target from 70% to 50%; the HPA restores 26 replicas, ten remain Pending, and the report says the incident is not recovered. A later action caps replicas, but the run's maximum remediation score is only 0.25. Best-window P95 remains 47.5% above baseline. This case connects correct localization with an intervention assessed as failing to resolve the capacity problem.

In [Online Boutique productcatalogservice CPU headroom](grades/online-boutique/runs/20260921-161532-online-boutique-pod-productcatalogservice-cpu-headroom-all-one-hour-364220b4/grade.json), RCA `5ca4d134-c823-4382-ac8a-b19a9abe1850` scores 0.8125. Matched remediation `6453a688-8353-48ef-b25f-c4c262e24660` has rubric score 0.7625, deductions totaling 1.0, and final score zero. It reports raising CPU request and limit from 250m to two cores, changing an unrelated service, and leaving 11 new catalog pods Pending. All four eligible remediation outputs score zero; best P95 is 108.6% above baseline. The penalty findings concern both scope and feasibility, while the report itself acknowledges incomplete rollout.

### 7.3 Scenario policy materially affects remediation grades

In [Online Boutique checkoutservice CPU headroom](grades/online-boutique/runs/20260921-142757-online-boutique-pod-checkoutservice-cpu-headroom-all-one-hour-1f2f3d2f/grade.json), remediation jobs `274712a3-d7b0-49d2-9798-f8454cbde67f` and `a5bcc38b-0f5b-4091-a262-340b970abb75` each receive a perfect rubric score but a 0.5 deduction, leaving final scores of 0.5. Their reports raise CPU capacity with equal requests and limits. The scenario penalty requires request below limit; this is a reference-policy judgment, not a universal claim that equal CPU requests and limits are invalid. The run passes Best-Window Tolerance with P95 11.4% below baseline despite failing remediation semantic success.

The catalog-headroom follow-up also exposes a reference limitation: after a prior action raises CPU to two cores and leaves Pending pods, a later action reduces it to one core, while grading reasons compare that reduction with the original scenario's increase expectation. Static expectations and accumulated actions can interact. Low grades deserve examination in context; they should not automatically be treated as infallible labels of every later corrective step.

### 7.4 A high remediation score need not establish service recovery

In [Online Boutique currencyservice memory](grades/online-boutique/runs/20260921-085928-online-boutique-pod-currencyservice-memory-all-one-hour-db32774a/grade.json), RCA `a52a8235-f881-456b-9e4d-d911fd902670` scores 0.3375, while matched remediation `f95ffe91-45c2-46e1-809e-a59aafb32d99` scores 1.0. The remediation report describes raising memory request from 256Mi to 1536Mi and limit from 512Mi to 2Gi, with three ready replicas. It nevertheless labels recovery not recovered because Prometheus symptom queries returned empty results. The independently recomputed best window passes (P95 −1.7%). Neither the report score nor the favorable selected window resolves the causal recovery question.

In [Online Boutique node packet loss on worker 3](grades/online-boutique/runs/20260917-211100-online-boutique-node-loss-worker-3-one-hour-447da855/grade.json), remediation `c79d6974-8496-4dcc-80e5-2b05d7f812c0` scores 1.0 for reporting isolation and evacuation of the affected node while preserving DaemonSets. The report explicitly keeps recovery unknown and leaves the node unschedulable pending diagnosis. Even the best frontend window remains 71.1% above baseline. This is an example of a semantically appropriate containment report without evidence of application recovery.

### 7.5 A good response can be followed by loss of focus

In [TeaStore auth memory](grades/teastore/runs/20260923-215850-teastore-pod-auth-memory-all-one-hour-06e773fa/grade.json), remediation `8c104209-3b2d-48b5-9262-eac610111081` scores 1.0 for a validation-only response that reports the required memory sizing already achieved. It completes 7.68 minutes after chaos starts. The six later scored remediation outputs all score zero and primarily target recommender probes or rollout settings. The remediation mean is only 0.1625, despite the perfect maximum. Best-window latency remains 63.7% above baseline. Appropriate restraint in one report does not establish sustained focus or acceptable service.

In [Sock Shop payment CPU](grades/sock-shop/runs/20260916-025047-sock-shop-pod-payment-cpu-all-one-hour-a72bcbd1/grade.json), ten scored RCA outputs reach only 0.475, while all eight scored remediation outputs are zero. Reports repeatedly shift toward queue-master runtime problems, node issues, and RabbitMQ effects. Remediation `f4d0dbdf-bb06-4981-b874-995c0d1c4d72` receives 1.25 in deductions for the reported intervention scope and failure to add expected CPU capacity. A later queue-master CPU change also receives a penalty for targeting another workload. Best-window latency is nevertheless 1.0% below baseline. This is a mismatch between reference-conditioned semantic performance and a favorable selected frontend period; it does not prove that every secondary symptom was fictitious.

In [TeaStore recommender bandwidth](grades/teastore/runs/20260923-235351-teastore-pod-recommender-bandwidth-all-one-hour-6fe6820f/grade.json), nine RCA outputs reach only 0.275 and all nine remediation outputs are zero. The highest RCA, `4b727a95-8bb8-4d30-bc62-2a662e9db7cf`, discusses auth-to-persistence timeouts while treating recommender as unaffected. Remediation reports move among auth and webui resource, restart, scaling, and configuration changes, each receiving a penalty for acting outside the expected target. The best frontend window is within tolerance (+1.3% P95). Repeated action and changing hypotheses do not establish correction of the scenario condition.

## 8. Implications for the paper and thesis

The results fit the agreed contribution of **an end-to-end benchmark plus an integrated reference SRE agent system**. The benchmark makes heterogeneous incident trajectories inspectable: some repeatedly investigate without intervening, some localize the condition but choose weak actions, some attain a strong report while service remains degraded, and some retain acceptable frontend windows without a strong diagnosis. These observations motivate reporting both Semantic Assessment and Performance Comparison.

For the three implemented capabilities, the empirical scope is:

1. **Configurable experimental framework:** the dataset exercises three applications and multiple infrastructure and service-level disturbance families with archived workload, placement, fault, and timing inputs. This demonstrates breadth of exercised configurations, not statistical repeatability or equivalent severity across them.
2. **Detection-triggered reference response:** the archives contain multiple RCA/remediation outputs and explicit decisions to act or decline action. Their variation supports studying the complete workflow. It does not measure detector precision/recall, establish missed detections, or isolate the effect of detector configuration. No detector ablation or alternative-response-system comparison is established by this cohort.
3. **Evidence capture and offline assessment:** semantic quality and frontend windows reveal disagreements that a single completion flag would conceal. The analysis also exposes missing final outputs, selector problems in historical summaries, and reference-conditioned penalties. This demonstrates inspectability while making the assessment's limitations visible.

A defensible central results statement is:

> Across 65 selected completed scenario runs, the reference system attained at least one RCA score above 0.8 in 46 of 64 semantically evaluable scenarios and at least one remediation score above 0.8 in 27 of 60. These maxima contrasted with low successful-session fractions and frontend behavior: 44 of 65 runs satisfied Best-Window Tolerance. The results show that diagnostic attainment, assessed corrective responses, and acceptable service windows capture different aspects of the incident trajectory.

The paper can lead with application-level semantic and performance tables, then use the matched worker-2 comparison, the bandwidth contrast, and the headroom baseline example to explain application differences. Node delay versus packet loss and two matched-workflow cases can connect these differences to response behavior. The thesis can expand the family-level comparison, no-action trajectories, score-policy interactions, and detailed scenario tables. Neither should call the Window Tolerance fraction a recovery rate or use Time to Maximum Score as mean time to recovery.

## 9. Limitations and evidence boundaries

- **Selection and replication:** the analysis conditions on completed execution and selects one run per scenario. It does not estimate operational reliability. There are no repeated completed trials of the same scenario in this cohort from which to estimate run-to-run variability. Session counts and overlapping windows do not supply independent replicates.
- **Reference-conditioned semantics:** expectations are LLM-assisted and author-guided, with no documented independent expert labeling or multi-rater validation. One judge configuration is used. The reports and policy can disagree with runtime state or with reasonable alternative interventions. Scores are assessments under this rubric, not exhaustive ground truth.
- **Behavioral sampling:** representative cases explain patterns but are not a systematic human-coded trajectory evaluation. Final reports can omit or misstate actions; this analysis does not verify every mutation against tool traces or cluster state.
- **Timing and initiation:** the reported timing ends at output completion and starts at chaos activation. It does not decompose detector latency, dispatch delay, execution time, or learning effects. No-response-in-scope cases cannot be assigned a detector failure without additional evidence.
- **Extremum selection and fault timing:** maxima and best windows benefit from repeated opportunities. Selected windows are not fixed post-action assessments. Recurring faults, natural platform behavior, earlier interventions, and fault expiry may explain changes. Scheduled cleanup is excluded by the interval boundary, but that does not establish continuous disturbance inside it.
- **Performance scope:** frontend rolling P95 and absolute 5xx rate do not measure every service, request journey, error fraction, or successful throughput. Missing-5xx imputation affects some passing windows. Low errors per second can accompany lower achieved traffic.
- **Comparability and provenance:** workloads and architectures differ across applications; the historical response-model revision and exact judge model revision are not established. These gaps should be resolved before controlled model comparisons or reproduction claims.

These limitations do not erase the observed results. They determine which conclusions the current evidence supports: descriptive behavior and stage-specific outcomes under archived conditions, rather than causal intervention benefit or universal agent capability.

## 10. Detailed scenario results

The tables below cover every completed selected run. Scenario labels omit the application prefix and trailing `-one-hour`; links point to the exact grade file, whose run directory also identifies the matching archive. `—` means unavailable, not zero. `N/Ns` means in-scope Session Count / Scored Session Count. Score pairs are maximum / mean; times are Time to Maximum Score in minutes. Each scenario is one run, regardless of its number of sessions.

Performance tables show baseline and selected paired values, absolute differences, and percentage changes. `L` is mean rolling P95 in seconds; `E` is mean 5xx in requests/s. `H` is Window Tolerance. A missing best window with `H=No` denotes rejection of all covered candidates by the error ceiling. Display rounding does not determine threshold classification; the helper uses unrounded values.

### Online Boutique: agent-output metrics

| Scenario | RCA max / mean | RCA N/Ns | RCA time | Remediation max / mean | Remediation N/Ns | Remediation time |
| --- | --- | --- | --- | --- | --- | --- |
| [node-cpu-worker-2](grades/online-boutique/runs/20260918-075737-online-boutique-node-cpu-worker-2-one-hour-842bd119/grade.json) | 1.0000 / 0.7146 | 6/6 | 13.39 | 0.6875 / 0.4042 | 4/3 | 16.28 |
| [node-delay-worker-2](grades/online-boutique/runs/20260917-135646-online-boutique-node-delay-worker-2-one-hour-e5daaf4c/grade.json) | 1.0000 / 0.4578 | 8/8 | 12.86 | 1.0000 / 0.3937 | 7/6 | 13.97 |
| [node-delay-worker-3](grades/online-boutique/runs/20260917-120727-online-boutique-node-delay-worker-3-one-hour-00dd0d05/grade.json) | 1.0000 / 0.3920 | 11/11 | 7.52 | 0.3500 / 0.2250 | 6/2 | 32.12 |
| [node-delay-worker-5](grades/online-boutique/runs/20260917-154538-online-boutique-node-delay-worker-5-one-hour-77c0a6e6/grade.json) | 1.0000 / 0.2106 | 13/13 | 5.80 | 0.9625 / 0.7875 | 2/2 | 16.38 |
| [node-loss-worker-1](grades/online-boutique/runs/20260917-173444-online-boutique-node-loss-worker-1-one-hour-4c1b1ce8/grade.json) | 1.0000 / 0.4375 | 5/5 | 13.36 | 0.1000 / 0.0500 | 5/2 | 8.64 |
| [node-loss-worker-2](grades/online-boutique/runs/20260917-192242-online-boutique-node-loss-worker-2-one-hour-de0ca92c/grade.json) | 0.5000 / 0.2075 | 5/5 | 7.37 | 0.5250 / 0.3219 | 4/4 | 9.06 |
| [node-loss-worker-3](grades/online-boutique/runs/20260917-211100-online-boutique-node-loss-worker-3-one-hour-447da855/grade.json) | 1.0000 / 0.8938 | 4/4 | 14.64 | 1.0000 / 0.5958 | 4/3 | 58.43 |
| [node-memory-worker-3](grades/online-boutique/runs/20260921-014211-online-boutique-node-memory-worker-3-one-hour-e682c0c4/grade.json) | 0.6500 / 0.4271 | 12/12 | 39.27 | 1.0000 / 0.2875 | 6/6 | 26.45 |
| [pod-adservice-memory-all](grades/online-boutique/runs/20260921-033053-online-boutique-pod-adservice-memory-all-one-hour-88df5666/grade.json) | 0.5000 / 0.1232 | 7/7 | 19.45 | 0.0000 / 0.0000 | 4/3 | 14.58 |
| [pod-cartservice-cpu-all](grades/online-boutique/runs/20260921-180412-online-boutique-pod-cartservice-cpu-all-one-hour-bb3fd8da/grade.json) | 1.0000 / 0.8333 | 9/9 | 9.31 | 0.8375 / 0.5139 | 9/9 | 18.42 |
| [pod-checkoutservice-cpu-all](grades/online-boutique/runs/20260917-230350-online-boutique-pod-checkoutservice-cpu-all-one-hour-0c3ef708/grade.json) | 1.0000 / 0.8107 | 7/7 | 10.08 | 0.9125 / 0.5589 | 7/7 | 30.21 |
| [pod-checkoutservice-cpu-headroom-all](grades/online-boutique/runs/20260921-142757-online-boutique-pod-checkoutservice-cpu-headroom-all-one-hour-1f2f3d2f/grade.json) | 0.8750 / 0.4925 | 5/5 | 19.14 | 0.5000 / 0.2500 | 4/4 | 7.02 |
| [pod-currencyservice-memory-all](grades/online-boutique/runs/20260921-085928-online-boutique-pod-currencyservice-memory-all-one-hour-db32774a/grade.json) | 0.5875 / 0.2500 | 8/8 | 8.91 | 1.0000 / 0.3281 | 4/4 | 21.08 |
| [pod-emailservice-cpu-headroom-all](grades/online-boutique/runs/20260921-124008-online-boutique-pod-emailservice-cpu-headroom-all-one-hour-15d02617/grade.json) | 0.6875 / 0.2031 | 8/8 | 30.30 | 0.4000 / 0.1000 | 4/4 | 20.49 |
| [pod-paymentservice-capacity-loss](grades/online-boutique/runs/20260921-105202-online-boutique-pod-paymentservice-capacity-loss-one-hour-09050beb/grade.json) | 1.0000 / 0.7281 | 8/8 | 26.25 | 0.7250 / 0.2984 | 8/8 | 58.17 |
| [pod-paymentservice-cpu-all](grades/online-boutique/runs/20260918-060816-online-boutique-pod-paymentservice-cpu-all-one-hour-f96645fb/grade.json) | 1.0000 / 0.6536 | 7/7 | 16.55 | 0.8500 / 0.4571 | 7/7 | 12.65 |
| [pod-productcatalogservice-bandwidth-all](grades/online-boutique/runs/20260921-052319-online-boutique-pod-productcatalogservice-bandwidth-all-one-hour-b7a779ab/grade.json) | 0.2375 / 0.1509 | 14/14 | 9.87 | — / — | 0/0 | — |
| [pod-productcatalogservice-cpu-all](grades/online-boutique/runs/20260918-041909-online-boutique-pod-productcatalogservice-cpu-all-one-hour-0994b3e1/grade.json) | 1.0000 / 0.8600 | 10/10 | 9.15 | 1.0000 / 0.5078 | 9/8 | 33.08 |
| [pod-productcatalogservice-cpu-headroom-all](grades/online-boutique/runs/20260921-161532-online-boutique-pod-productcatalogservice-cpu-headroom-all-one-hour-364220b4/grade.json) | 0.8125 / 0.5000 | 4/4 | 18.76 | 0.0000 / 0.0000 | 4/4 | 5.12 |
| [pod-recommendationservice-cpu-all](grades/online-boutique/runs/20260918-005141-online-boutique-pod-recommendationservice-cpu-all-one-hour-ea84314b/grade.json) | 1.0000 / 0.5304 | 7/7 | 18.65 | 0.2500 / 0.0604 | 6/6 | 25.56 |
| [pod-redis-cart-memory-all](grades/online-boutique/runs/20260921-071113-online-boutique-pod-redis-cart-memory-all-one-hour-add707a0/grade.json) | 0.8125 / 0.2350 | 5/5 | 11.95 | 0.0875 / 0.0292 | 3/3 | 14.24 |

### Online Boutique: baseline reference

| Scenario | Baseline L (s) | Baseline E (requests/s) | Imputed baseline 5xx samples |
| --- | --- | --- | --- |
| node-cpu-worker-2 | 0.0983 | 0.0262 | 0 |
| node-delay-worker-2 | 0.1042 | 0.0280 | 0 |
| node-delay-worker-3 | 0.1029 | 0.0278 | 0 |
| node-delay-worker-5 | 0.0994 | 0.0278 | 0 |
| node-loss-worker-1 | 0.1005 | 0.0234 | 0 |
| node-loss-worker-2 | 0.1054 | 0.0258 | 0 |
| node-loss-worker-3 | 0.0983 | 0.0220 | 0 |
| node-memory-worker-3 | 0.1016 | 0.0287 | 0 |
| pod-adservice-memory-all | 0.1046 | 0.0234 | 0 |
| pod-cartservice-cpu-all | 0.0997 | 0.0256 | 0 |
| pod-checkoutservice-cpu-all | 0.0999 | 0.0272 | 0 |
| pod-checkoutservice-cpu-headroom-all | 0.1085 | 0.0291 | 0 |
| pod-currencyservice-memory-all | 0.0982 | 0.0298 | 0 |
| pod-emailservice-cpu-headroom-all | 0.1352 | 0.0282 | 0 |
| pod-paymentservice-capacity-loss | 0.1043 | 0.0290 | 0 |
| pod-paymentservice-cpu-all | 0.1039 | 0.0256 | 0 |
| pod-productcatalogservice-bandwidth-all | 0.1089 | 0.0233 | 0 |
| pod-productcatalogservice-cpu-all | 0.0979 | 0.0316 | 0 |
| pod-productcatalogservice-cpu-headroom-all | 0.1087 | 0.0345 | 0 |
| pod-recommendationservice-cpu-all | 0.0981 | 0.0288 | 0 |
| pod-redis-cart-memory-all | 0.1114 | 0.0280 | 0 |

### Online Boutique: paired five-minute windows

| Scenario | L (s) | ΔL (s) | ΔL (%) | E (requests/s) | ΔE (requests/s) | ΔE (%) | H |
| --- | --- | --- | --- | --- | --- | --- | --- |
| node-cpu-worker-2 | 0.0936 | -0.0048 | -4.9 | 0.0431 | 0.0169 | 64.5 | Yes |
| node-delay-worker-2 | 0.0974 | -0.0069 | -6.6 | 0.0234 | -0.0046 | -16.6 | Yes |
| node-delay-worker-3 | 0.1068 | 0.0040 | 3.9 | 0.0346 | 0.0068 | 24.5 | Yes |
| node-delay-worker-5 | 0.0938 | -0.0056 | -5.6 | 0.0377 | 0.0099 | 35.8 | Yes |
| node-loss-worker-1 | 0.4451 | 0.3446 | 342.7 | 0.0142 | -0.0093 | -39.5 | No |
| node-loss-worker-2 | 0.3854 | 0.2801 | 265.8 | 0.0326 | 0.0069 | 26.6 | No |
| node-loss-worker-3 | 0.1682 | 0.0699 | 71.1 | 0.0548 | 0.0328 | 148.9 | No |
| node-memory-worker-3 | 0.0952 | -0.0064 | -6.3 | 0.0383 | 0.0096 | 33.5 | Yes |
| pod-adservice-memory-all | 0.0996 | -0.0050 | -4.8 | 0.0191 | -0.0043 | -18.4 | Yes |
| pod-cartservice-cpu-all | 0.1034 | 0.0037 | 3.7 | 0.0210 | -0.0045 | -17.6 | Yes |
| pod-checkoutservice-cpu-all | 0.1505 | 0.0506 | 50.6 | 0.0299 | 0.0027 | 9.7 | No |
| pod-checkoutservice-cpu-headroom-all | 0.0961 | -0.0124 | -11.4 | 0.0275 | -0.0016 | -5.4 | Yes |
| pod-currencyservice-memory-all | 0.0966 | -0.0017 | -1.7 | 0.0304 | 0.0006 | 2.1 | Yes |
| pod-emailservice-cpu-headroom-all | 0.1168 | -0.0184 | -13.6 | 0.0290 | 0.0009 | 3.1 | Yes |
| pod-paymentservice-capacity-loss | — | — | — | — | — | — | No |
| pod-paymentservice-cpu-all | 0.1705 | 0.0667 | 64.2 | 0.0475 | 0.0220 | 86.0 | No |
| pod-productcatalogservice-bandwidth-all | 0.1039 | -0.0050 | -4.6 | 0.0144 | -0.0089 | -38.3 | Yes |
| pod-productcatalogservice-cpu-all | 0.1741 | 0.0763 | 77.9 | 0.0234 | -0.0082 | -26.0 | No |
| pod-productcatalogservice-cpu-headroom-all | 0.2268 | 0.1181 | 108.6 | 0.0070 | -0.0275 | -79.8 | No |
| pod-recommendationservice-cpu-all | 0.1446 | 0.0466 | 47.5 | 0.0286 | -0.0002 | -0.7 | No |
| pod-redis-cart-memory-all | 0.0973 | -0.0141 | -12.7 | 0.0268 | -0.0013 | -4.5 | Yes |

### Sock Shop: agent-output metrics

| Scenario | RCA max / mean | RCA N/Ns | RCA time | Remediation max / mean | Remediation N/Ns | Remediation time |
| --- | --- | --- | --- | --- | --- | --- |
| [node-cpu-worker-2](grades/sock-shop/runs/20260916-044232-sock-shop-node-cpu-worker-2-one-hour-e7fb3d20/grade.json) | 1.0000 / 0.6458 | 9/9 | 54.88 | 0.9625 / 0.5232 | 7/7 | 56.76 |
| [node-delay-worker-2](grades/sock-shop/runs/20260915-085323-sock-shop-node-delay-worker-2-one-hour-6d3be870/grade.json) | 1.0000 / 0.3175 | 10/10 | 14.82 | 0.6750 / 0.1214 | 8/7 | 17.47 |
| [node-delay-worker-3](grades/sock-shop/runs/20260915-070028-sock-shop-node-delay-worker-3-one-hour-f8cea5b7/grade.json) | 0.9375 / 0.8875 | 3/3 | 7.01 | 1.0000 / 0.6667 | 3/3 | 8.56 |
| [node-delay-worker-5](grades/sock-shop/runs/20260915-104631-sock-shop-node-delay-worker-5-one-hour-c594d88b/grade.json) | 1.0000 / 0.7179 | 7/7 | 5.74 | 1.0000 / 0.6225 | 5/5 | 13.89 |
| [node-loss-worker-1](grades/sock-shop/runs/20260915-123927-sock-shop-node-loss-worker-1-one-hour-0a72f966/grade.json) | 0.6750 / 0.2091 | 11/11 | 15.87 | 0.8750 / 0.3679 | 8/7 | 17.73 |
| [node-loss-worker-2](grades/sock-shop/runs/20260915-143132-sock-shop-node-loss-worker-2-one-hour-643fe312/grade.json) | 0.9375 / 0.2922 | 8/8 | 27.66 | 0.7500 / 0.3797 | 8/8 | 30.90 |
| [node-loss-worker-3](grades/sock-shop/runs/20260915-162308-sock-shop-node-loss-worker-3-one-hour-9fb87ae1/grade.json) | 1.0000 / 0.4550 | 5/5 | 43.07 | 0.5500 / 0.1833 | 3/3 | 36.84 |
| [node-memory-worker-3](grades/sock-shop/runs/20260916-063430-sock-shop-node-memory-worker-3-one-hour-7bec91aa/grade.json) | — / — | 0/0 | — | — / — | 0/0 | — |
| [pod-carts-cpu-all](grades/sock-shop/runs/20260915-181504-sock-shop-pod-carts-cpu-all-one-hour-d9ce8582/grade.json) | 0.8625 / 0.4433 | 15/15 | 13.97 | — / — | 0/0 | — |
| [pod-carts-db-memory-all](grades/sock-shop/runs/20260916-140121-sock-shop-pod-carts-db-memory-all-one-hour-d1b6af93/grade.json) | 1.0000 / 0.2597 | 9/9 | 9.60 | 0.5875 / 0.0979 | 9/6 | 10.69 |
| [pod-catalogue-bandwidth-all](grades/sock-shop/runs/20260916-120946-sock-shop-pod-catalogue-bandwidth-all-one-hour-5602bb98/grade.json) | 0.1125 / 0.0375 | 3/3 | 31.73 | — / — | 0/0 | — |
| [pod-catalogue-cpu-all](grades/sock-shop/runs/20260915-235020-sock-shop-pod-catalogue-cpu-all-one-hour-72f06623/grade.json) | 0.8875 / 0.5538 | 13/13 | 9.41 | 1.0000 / 0.9083 | 3/3 | 10.87 |
| [pod-catalogue-cpu-headroom-all](grades/sock-shop/runs/20260917-085658-sock-shop-pod-catalogue-cpu-headroom-all-one-hour-a4bb7faa/grade.json) | 0.9500 / 0.4236 | 9/9 | 8.05 | 0.4250 / 0.1766 | 8/8 | 10.29 |
| [pod-front-end-cpu-headroom-all](grades/sock-shop/runs/20260917-050755-sock-shop-pod-front-end-cpu-headroom-all-one-hour-ca4e5837/grade.json) | 1.0000 / 0.5604 | 6/6 | 17.34 | 1.0000 / 0.4750 | 6/6 | 3.76 |
| [pod-orders-capacity-loss](grades/sock-shop/runs/20260916-101803-sock-shop-pod-orders-capacity-loss-one-hour-24096e3c/grade.json) | 1.0000 / 0.7750 | 6/6 | 14.82 | 0.3875 / 0.1850 | 6/5 | 48.30 |
| [pod-orders-cpu-all](grades/sock-shop/runs/20260915-200700-sock-shop-pod-orders-cpu-all-one-hour-e659c343/grade.json) | 1.0000 / 0.6406 | 4/4 | 6.09 | 0.8750 / 0.8750 | 1/1 | 8.94 |
| [pod-orders-cpu-headroom-all](grades/sock-shop/runs/20260917-070236-sock-shop-pod-orders-cpu-headroom-all-one-hour-e0f89a80/grade.json) | 0.9250 / 0.5306 | 9/9 | 12.85 | 0.7375 / 0.1500 | 9/8 | 15.32 |
| [pod-payment-capacity-loss](grades/sock-shop/runs/20260916-193636-sock-shop-pod-payment-capacity-loss-one-hour-fe747c4d/grade.json) | 0.8625 / 0.5250 | 7/7 | 38.00 | 0.4500 / 0.1375 | 7/7 | 59.06 |
| [pod-payment-cpu-all](grades/sock-shop/runs/20260916-025047-sock-shop-pod-payment-cpu-all-one-hour-a72bcbd1/grade.json) | 0.4750 / 0.2237 | 10/10 | 4.46 | 0.0000 / 0.0000 | 8/8 | 11.43 |
| [pod-shipping-bandwidth-all](grades/sock-shop/runs/20260916-174500-sock-shop-pod-shipping-bandwidth-all-one-hour-02fe1a50/grade.json) | 0.0000 / 0.0000 | 1/1 | 27.94 | — / — | 0/0 | — |
| [pod-shipping-memory-all](grades/sock-shop/runs/20260916-082631-sock-shop-pod-shipping-memory-all-one-hour-a23a2506/grade.json) | 0.8875 / 0.6125 | 4/4 | 13.75 | 1.0000 / 0.7625 | 3/3 | 15.75 |
| [pod-user-cpu-all](grades/sock-shop/runs/20260915-215839-sock-shop-pod-user-cpu-all-one-hour-76bd5381/grade.json) | 1.0000 / 0.4937 | 12/12 | 5.24 | 0.9625 / 0.4688 | 4/4 | 35.23 |
| [pod-user-memory-all](grades/sock-shop/runs/20260916-155256-sock-shop-pod-user-memory-all-one-hour-aa79aa40/grade.json) | 1.0000 / 0.4750 | 8/8 | 6.39 | 1.0000 / 0.8281 | 4/4 | 10.20 |

### Sock Shop: baseline reference

| Scenario | Baseline L (s) | Baseline E (requests/s) | Imputed baseline 5xx samples |
| --- | --- | --- | --- |
| node-cpu-worker-2 | 0.0948 | 0.0000 | 0 |
| node-delay-worker-2 | 0.0960 | 0.0000 | 0 |
| node-delay-worker-3 | 0.0955 | 0.0000 | 100 |
| node-delay-worker-5 | 0.0953 | 0.0000 | 100 |
| node-loss-worker-1 | 0.0958 | 0.0000 | 0 |
| node-loss-worker-2 | 0.0949 | 0.0000 | 100 |
| node-loss-worker-3 | 0.0946 | 0.0000 | 0 |
| node-memory-worker-3 | 0.0953 | 0.0000 | 100 |
| pod-carts-cpu-all | 0.0941 | 0.0000 | 100 |
| pod-carts-db-memory-all | 0.0929 | 0.0000 | 0 |
| pod-catalogue-bandwidth-all | 0.0937 | 0.0000 | 0 |
| pod-catalogue-cpu-all | 0.0950 | 0.0000 | 0 |
| pod-catalogue-cpu-headroom-all | 0.4451 | 0.0552 | 0 |
| pod-front-end-cpu-headroom-all | 0.4440 | 0.0248 | 0 |
| pod-orders-capacity-loss | 0.0940 | 0.0000 | 100 |
| pod-orders-cpu-all | 0.0945 | 0.0000 | 100 |
| pod-orders-cpu-headroom-all | 0.4704 | 0.0000 | 0 |
| pod-payment-capacity-loss | 0.0940 | 0.0000 | 0 |
| pod-payment-cpu-all | 0.0963 | 0.0000 | 0 |
| pod-shipping-bandwidth-all | 0.0929 | 0.0000 | 100 |
| pod-shipping-memory-all | 0.0934 | 0.0000 | 0 |
| pod-user-cpu-all | 0.0968 | 0.0000 | 0 |
| pod-user-memory-all | 0.0926 | 0.0000 | 100 |

### Sock Shop: paired five-minute windows

| Scenario | L (s) | ΔL (s) | ΔL (%) | E (requests/s) | ΔE (requests/s) | ΔE (%) | H |
| --- | --- | --- | --- | --- | --- | --- | --- |
| node-cpu-worker-2 | 0.0696 | -0.0253 | -26.6 | 0.0000 | 0.0000 | — | Yes |
| node-delay-worker-2 | 0.0786 | -0.0175 | -18.2 | 0.0000 | 0.0000 | — | Yes |
| node-delay-worker-3 | 0.0950 | -0.0004 | -0.5 | 0.0000 | 0.0000 | — | Yes |
| node-delay-worker-5 | 0.0930 | -0.0023 | -2.4 | 0.0000 | 0.0000 | — | Yes |
| node-loss-worker-1 | 0.1403 | 0.0445 | 46.5 | 0.0000 | 0.0000 | — | No |
| node-loss-worker-2 | 0.1000 | 0.0051 | 5.4 | 0.0000 | 0.0000 | — | Yes |
| node-loss-worker-3 | 0.0946 | -0.0000 | -0.0 | 0.0000 | 0.0000 | — | Yes |
| node-memory-worker-3 | 0.0931 | -0.0022 | -2.3 | 0.0000 | 0.0000 | — | Yes |
| pod-carts-cpu-all | 0.0930 | -0.0011 | -1.2 | 0.0000 | 0.0000 | — | Yes |
| pod-carts-db-memory-all | 0.0923 | -0.0006 | -0.6 | 0.0000 | 0.0000 | — | Yes |
| pod-catalogue-bandwidth-all | 0.0931 | -0.0006 | -0.6 | 0.0000 | 0.0000 | — | Yes |
| pod-catalogue-cpu-all | 0.0979 | 0.0029 | 3.0 | 0.0000 | 0.0000 | — | Yes |
| pod-catalogue-cpu-headroom-all | 0.1224 | -0.3227 | -72.5 | 0.0000 | -0.0552 | -100.0 | Yes |
| pod-front-end-cpu-headroom-all | 0.1010 | -0.3431 | -77.3 | 0.0000 | -0.0248 | -100.0 | Yes |
| pod-orders-capacity-loss | 0.1070 | 0.0130 | 13.8 | 0.1133 | 0.1133 | — | Yes |
| pod-orders-cpu-all | 0.1031 | 0.0086 | 9.1 | 0.0000 | 0.0000 | — | Yes |
| pod-orders-cpu-headroom-all | 0.0950 | -0.3754 | -79.8 | 0.0000 | 0.0000 | — | Yes |
| pod-payment-capacity-loss | — | — | — | — | — | — | No |
| pod-payment-cpu-all | 0.0953 | -0.0010 | -1.0 | 0.0251 | 0.0251 | — | Yes |
| pod-shipping-bandwidth-all | 0.0917 | -0.0011 | -1.2 | 0.0000 | 0.0000 | — | Yes |
| pod-shipping-memory-all | 0.0925 | -0.0009 | -1.0 | 0.0000 | 0.0000 | — | Yes |
| pod-user-cpu-all | 0.0981 | 0.0013 | 1.3 | 0.0377 | 0.0377 | — | Yes |
| pod-user-memory-all | 0.0922 | -0.0005 | -0.5 | 0.0000 | 0.0000 | — | Yes |

### TeaStore: agent-output metrics

| Scenario | RCA max / mean | RCA N/Ns | RCA time | Remediation max / mean | Remediation N/Ns | Remediation time |
| --- | --- | --- | --- | --- | --- | --- |
| [node-cpu-worker-2](grades/teastore/runs/20260922-155606-teastore-node-cpu-worker-2-one-hour-5f003308/grade.json) | 0.4250 / 0.2278 | 9/9 | 13.75 | 0.2875 / 0.1109 | 9/8 | 34.85 |
| [node-delay-worker-2](grades/teastore/runs/20260921-214910-teastore-node-delay-worker-2-one-hour-b007dcff/grade.json) | 1.0000 / 0.3982 | 7/7 | 8.45 | 1.0000 / 0.5250 | 4/4 | 10.46 |
| [node-delay-worker-3](grades/teastore/runs/20260921-195245-teastore-node-delay-worker-3-one-hour-c4acec7f/grade.json) | 1.0000 / 0.4016 | 8/8 | 7.73 | 1.0000 / 0.3797 | 8/8 | 10.46 |
| [node-delay-worker-4](grades/teastore/runs/20260921-234204-teastore-node-delay-worker-4-one-hour-4b0744a3/grade.json) | 1.0000 / 0.5482 | 7/7 | 7.23 | 1.0000 / 0.3821 | 7/7 | 33.20 |
| [node-loss-worker-1](grades/teastore/runs/20260922-013828-teastore-node-loss-worker-1-one-hour-efaa6a50/grade.json) | 0.1750 / 0.1313 | 4/4 | 28.70 | 0.3500 / 0.1500 | 4/3 | 24.58 |
| [node-loss-worker-2](grades/teastore/runs/20260923-083754-teastore-node-loss-worker-2-one-hour-dee25055/grade.json) | 0.2750 / 0.1708 | 9/9 | 53.42 | 0.4000 / 0.2056 | 9/9 | 11.66 |
| [node-loss-worker-3](grades/teastore/runs/20260923-103011-teastore-node-loss-worker-3-one-hour-d497fecd/grade.json) | 0.4750 / 0.2042 | 6/6 | 16.12 | 0.5000 / 0.2225 | 5/5 | 34.66 |
| [pod-auth-cpu-all](grades/teastore/runs/20260923-122633-teastore-pod-auth-cpu-all-one-hour-65b4362f/grade.json) | 1.0000 / 0.5969 | 8/8 | 49.44 | 0.5375 / 0.1250 | 8/8 | 11.36 |
| [pod-auth-memory-all](grades/teastore/runs/20260923-215850-teastore-pod-auth-memory-all-one-hour-06e773fa/grade.json) | 0.9375 / 0.2708 | 9/9 | 7.18 | 1.0000 / 0.1625 | 9/8 | 7.68 |
| [pod-db-memory-all](grades/teastore/runs/20260923-200154-teastore-pod-db-memory-all-one-hour-e44b47ed/grade.json) | 1.0000 / 0.2514 | 9/9 | 34.61 | 0.3000 / 0.0656 | 9/8 | 37.12 |
| [pod-image-bandwidth-all](grades/teastore/runs/20260923-180616-teastore-pod-image-bandwidth-all-one-hour-b6362ec3/grade.json) | 0.2375 / 0.1437 | 10/10 | 46.36 | 0.2000 / 0.0571 | 9/7 | 12.60 |
| [pod-image-cpu-all](grades/teastore/runs/20260922-120118-teastore-pod-image-cpu-all-one-hour-60af58c4/grade.json) | 0.9250 / 0.4250 | 8/8 | 47.26 | 0.9125 / 0.3078 | 8/8 | 24.76 |
| [pod-image-cpu-headroom-all](grades/teastore/runs/20260924-081400-teastore-pod-image-cpu-headroom-all-one-hour-dc9c3753/grade.json) | 0.3375 / 0.1661 | 7/7 | 49.32 | 0.0000 / 0.0000 | 6/6 | 5.64 |
| [pod-image-memory-all](grades/teastore/runs/20260922-193835-teastore-pod-image-memory-all-one-hour-5be7bdb4/grade.json) | 1.0000 / 0.2762 | 10/10 | 7.09 | 1.0000 / 0.1250 | 8/8 | 8.51 |
| [pod-persistence-capacity-loss](grades/teastore/runs/20260922-213102-teastore-pod-persistence-capacity-loss-one-hour-58811f6e/grade.json) | 1.0000 / 0.6359 | 8/8 | 21.79 | 0.6875 / 0.1688 | 8/8 | 52.35 |
| [pod-persistence-cpu-all](grades/teastore/runs/20260923-142216-teastore-pod-persistence-cpu-all-one-hour-e8220b21/grade.json) | 1.0000 / 0.6694 | 9/9 | 12.51 | 1.0000 / 0.5141 | 9/8 | 49.03 |
| [pod-persistence-cpu-headroom-all](grades/teastore/runs/20260924-062057-teastore-pod-persistence-cpu-headroom-all-one-hour-fa2a43dd/grade.json) | 0.8125 / 0.3018 | 7/7 | 30.57 | 0.3000 / 0.0429 | 7/7 | 22.70 |
| [pod-recommender-bandwidth-all](grades/teastore/runs/20260923-235351-teastore-pod-recommender-bandwidth-all-one-hour-6fe6820f/grade.json) | 0.2750 / 0.1542 | 9/9 | 13.91 | 0.0000 / 0.0000 | 9/9 | 3.28 |
| [pod-recommender-cpu-all](grades/teastore/runs/20260922-100606-teastore-pod-recommender-cpu-all-one-hour-676929a5/grade.json) | 1.0000 / 0.6672 | 8/8 | 6.85 | 0.7000 / 0.3125 | 8/8 | 10.69 |
| [pod-registry-capacity-loss](grades/teastore/runs/20260924-014522-teastore-pod-registry-capacity-loss-one-hour-23799335/grade.json) | 1.0000 / 0.7425 | 10/10 | 30.23 | 1.0000 / 0.4458 | 9/9 | 45.06 |
| [pod-registry-cpu-all](grades/teastore/runs/20260922-135914-teastore-pod-registry-cpu-all-one-hour-60f39d3f/grade.json) | 0.6250 / 0.2528 | 9/9 | 24.27 | 0.1875 / 0.0482 | 7/7 | 58.38 |

### TeaStore: baseline reference

| Scenario | Baseline L (s) | Baseline E (requests/s) | Imputed baseline 5xx samples |
| --- | --- | --- | --- |
| node-cpu-worker-2 | 0.0536 | 0.0000 | 0 |
| node-delay-worker-2 | 0.0799 | 0.0000 | 0 |
| node-delay-worker-3 | 0.0585 | 0.0000 | 0 |
| node-delay-worker-4 | 0.0674 | 0.0000 | 0 |
| node-loss-worker-1 | 0.0603 | 0.0000 | 0 |
| node-loss-worker-2 | 0.0506 | 0.0000 | 0 |
| node-loss-worker-3 | 0.0595 | 0.0000 | 0 |
| pod-auth-cpu-all | 0.0494 | 0.0000 | 0 |
| pod-auth-memory-all | 0.0515 | 0.0000 | 0 |
| pod-db-memory-all | 0.0536 | 0.0000 | 0 |
| pod-image-bandwidth-all | 0.0545 | 0.0000 | 0 |
| pod-image-cpu-all | 0.0868 | 0.0000 | 0 |
| pod-image-cpu-headroom-all | 0.1911 | 0.0007 | 0 |
| pod-image-memory-all | 0.0614 | 0.0000 | 0 |
| pod-persistence-capacity-loss | 0.0539 | 0.0000 | 0 |
| pod-persistence-cpu-all | 0.0566 | 0.0000 | 0 |
| pod-persistence-cpu-headroom-all | 0.0867 | 0.0000 | 0 |
| pod-recommender-bandwidth-all | 0.0471 | 0.0000 | 0 |
| pod-recommender-cpu-all | 0.0738 | 0.0000 | 0 |
| pod-registry-capacity-loss | 0.0475 | 0.0000 | 0 |
| pod-registry-cpu-all | 0.0611 | 0.0000 | 0 |

### TeaStore: paired five-minute windows

| Scenario | L (s) | ΔL (s) | ΔL (%) | E (requests/s) | ΔE (requests/s) | ΔE (%) | H |
| --- | --- | --- | --- | --- | --- | --- | --- |
| node-cpu-worker-2 | 0.0505 | -0.0031 | -5.8 | 0.0000 | 0.0000 | — | Yes |
| node-delay-worker-2 | 0.0544 | -0.0255 | -31.9 | 0.0000 | 0.0000 | — | Yes |
| node-delay-worker-3 | 0.0409 | -0.0176 | -30.1 | 0.1744 | 0.1744 | — | Yes |
| node-delay-worker-4 | 0.0506 | -0.0167 | -24.8 | 0.0000 | 0.0000 | — | Yes |
| node-loss-worker-1 | 0.3738 | 0.3135 | 519.9 | 0.0000 | 0.0000 | — | No |
| node-loss-worker-2 | 0.4423 | 0.3917 | 774.4 | 0.0067 | 0.0067 | — | No |
| node-loss-worker-3 | 0.3163 | 0.2568 | 431.7 | 0.0000 | 0.0000 | — | No |
| pod-auth-cpu-all | 0.0614 | 0.0120 | 24.3 | 0.0124 | 0.0124 | — | No |
| pod-auth-memory-all | 0.0843 | 0.0328 | 63.7 | 0.0000 | 0.0000 | — | No |
| pod-db-memory-all | 0.0482 | -0.0054 | -10.1 | 0.0000 | 0.0000 | — | Yes |
| pod-image-bandwidth-all | 4.3428 | 4.2883 | 7869.9 | 0.0000 | 0.0000 | — | No |
| pod-image-cpu-all | 0.0901 | 0.0032 | 3.7 | 0.0000 | 0.0000 | — | Yes |
| pod-image-cpu-headroom-all | 0.1418 | -0.0493 | -25.8 | 0.0000 | -0.0007 | -100.0 | Yes |
| pod-image-memory-all | 0.0503 | -0.0111 | -18.1 | 0.0000 | 0.0000 | — | Yes |
| pod-persistence-capacity-loss | 0.0416 | -0.0123 | -22.9 | 0.0000 | 0.0000 | — | Yes |
| pod-persistence-cpu-all | 0.0913 | 0.0347 | 61.4 | 0.0000 | 0.0000 | — | No |
| pod-persistence-cpu-headroom-all | 0.1841 | 0.0974 | 112.4 | 0.3414 | 0.3414 | — | No |
| pod-recommender-bandwidth-all | 0.0477 | 0.0006 | 1.3 | 0.0000 | 0.0000 | — | Yes |
| pod-recommender-cpu-all | 0.2016 | 0.1278 | 173.3 | 0.0102 | 0.0102 | — | No |
| pod-registry-capacity-loss | — | — | — | — | — | — | No |
| pod-registry-cpu-all | 0.0479 | -0.0133 | -21.7 | 0.0000 | 0.0000 | — | Yes |

## 11. Reproduction and review record

The numeric analysis calls the existing helper with the notebook defaults and correct namespace/workload pair for each application. After ordinary notebook selection, both selected scenario rows and session membership are restricted to `run_completed=True` for the primary cohort. No archived scripts, hooks, endpoints, or live infrastructure are used. The following sketch reproduces the aggregate population from the Grader directory in an environment with its Python dependencies:

```python
from pathlib import Path
from eda.report_metrics import ReportConfig, build_report, aggregate_report

root = Path.cwd()
for app, workload in {
    "online-boutique": "frontend",
    "sock-shop": "front-end",
    "teastore": "teastore-webui",
}.items():
    config = ReportConfig(
        score_threshold=0.8, p95_change_limit=0.20, max_5xx_rps=0.5,
        window_minutes=5.0, baseline_ignore_minutes=5.0,
        repeat_policy="latest_completed_else_latest",
        workload=workload, namespace=app,
    )
    attempts, selected, jobs = build_report(
        root / "grades" / app, root / "results" / app,
        config, include_ungraded=True,
    )
    selected = selected.loc[selected.run_completed].copy()
    jobs["selected"] = jobs.run.isin(selected.run)
    print(app, aggregate_report(selected, jobs, config).to_string(index=False))
```

Sources for definitions are [`grader/time_scope.py`](grader/time_scope.py), [`grader/window_comparison.py`](grader/window_comparison.py), the notebook helper, and each archived grade configuration. Framing follows the existing [paper methodology](../../../Paper/contents/04-EvaluationMethodology.tex), [thesis methodology](../../../Thesis/chapters/03_methodology.tex), and [user-authored introduction plan](../../../Paper/plan/01-Introduction.md), together with the workspace agreement. The relevant evaluation, results, and discussion plans are empty; all plan files were left unchanged.

The original analysis received internal reviews of metric definitions, selection, provenance, response cases, and matched application comparisons. This revision removes the retired window measurements from that analysis. It preserves the reported semantic and best-window values and the links to their source archives. These internal checks are not independent human peer review or empirical validation.
