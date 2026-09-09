# Paper evaluation plan

This plan defines the two headline numbers used to summarize the 46 currently
planned evaluation scenarios: 23 Online Boutique scenarios and 23 TeaStore
scenarios. The scenario catalogue is documented in
[`scenario.md`](scenario.md).

The calculations are implemented in
[`notebook/evaluation_metrics.ipynb`](../notebook/evaluation_metrics.ipynb),
with reusable calculation and presentation code beside it in Python modules.
Set the notebook's `GRADES_PATH` constant to the grader output directory to
analyze.

The evaluation should measure whether the autonomous incident loop eventually
diagnoses and safely remediates each incident within the fixed scenario window.
It should not average every intermediate hypothesis as if each were an
independent incident, and it should not report the single highest score across
the entire dataset.

The companion notebook also reports a configurable **Scenario Success Rate
(SSR)**. Set `SCENARIO_SUCCESS_SCORE_THRESHOLD` at the top of the notebook. A
graded scenario is successful when at least one succeeded, non-empty RCA
session and at least one succeeded, non-empty remediation session each have
`rubric.overall_score` greater than or equal to that threshold. Otherwise it is
failed. This is a score-only, best-achieved joint-quality measure: it does not
replace RSRR because it does not require safe execution or metric recovery.

## Headline numbers

Report these two percentages as the primary paper results:

1. **RCA Scenario Success Rate (RCA-SSR):** the percentage of evaluated
   scenarios in which the system produces at least one qualifying RCA within
   the scenario window.
2. **Remediation Scenario Recovery Rate (RSRR):** the percentage of evaluated
   scenarios in which the system executes at least one qualifying remediation
   that is semantically correct, non-harmful, and followed by metric recovery.

These are macro rates over scenarios. Every scenario contributes equal weight,
regardless of how many alerts, RCA jobs, or remediation jobs it generated.

## RCA success definition

An RCA job qualifies when all of the following hold:

- the job status is `succeeded` and it contains a non-empty final result;
- `alignment.verdict` is `aligned`, which means the rubric's
  `root_cause_correctness` score is at least `0.75`;
- it occurs within the fixed evaluation window for that scenario.

The scenario is an RCA success if at least one RCA job qualifies:

```text
RCA_success(scenario) = 1 if any RCA job qualifies, otherwise 0

RCA-SSR = sum(RCA_success(scenario)) / number_of_evaluated_scenarios * 100
```

This is an eventual-diagnosis measure. It allows the agent to investigate and
revise an early hypothesis without treating every intermediate attempt as a
separate failed incident. Use the **earliest** qualifying RCA—not the
highest-scoring RCA—to calculate attempts-to-success and time-to-RCA.

The weighted RCA rubric score should still be reported as a secondary quality
measure. This prevents a correct root-cause label with weak evidence or causal
reasoning from being presented as uniformly high-quality analysis.

## Remediation success definition

A remediation job qualifies when all of the following hold:

- the job status is `succeeded` and it contains a non-empty final result;
- `alignment.verdict` is `aligned`, which means the rubric's
  `remediation_correctness` score is at least `0.75`;
- `rubric.penalty_total` is `0`, so no executed harmful, unsafe,
  counterproductive, or simulation-cheating action was detected;
- `metrics.outcome` is `good`;
- `final_grade` is `good`;
- it occurs within the fixed evaluation window for that scenario.

The scenario is a remediation success if at least one remediation job
qualifies:

```text
Remediation_success(scenario) = 1 if any remediation job qualifies, otherwise 0

RSRR = sum(Remediation_success(scenario)) / number_of_evaluated_scenarios * 100
```

The metric outcome uses only the five-minute comparisons for
`response_time_p95_seconds` and `http_5xx_rate`. It is `good` when neither core
metric worsens and at least one improves by the configured threshold, currently
15 percent. Other captured metrics may support RCA and remediation assessment,
but they do not determine metric recovery.

Use the **earliest** qualifying remediation for time-to-recovery and
attempts-to-recovery. Do not choose the numerically highest remediation score
after observing all attempts.

## Multiple runs of the same scenario

If each scenario is executed once, the formulas above are simple success
fractions. If a scenario is repeated, first calculate its success proportion
across repetitions, then average those scenario proportions:

```text
scenario_RCA_rate(s) = successful_RCA_runs(s) / completed_runs(s)

RCA-SSR = mean of scenario_RCA_rate(s) across scenarios
```

Apply the same calculation to remediation. This prevents scenarios with more
repetitions from receiving greater weight and avoids the optimistic rule of
declaring a repeated scenario successful when only one of many repetitions
passes.

All compared systems must use the same scenario duration, alerting policy,
maximum workflow attempts, and stopping conditions. Otherwise an agent given
more attempts has an unfairly higher chance of eventually passing.

## Denominators and non-evaluable runs

Always publish the evaluated coverage beside the two headline rates:

```text
Scenario coverage = evaluated scenarios / 46 planned scenarios
```

Do not describe a result as covering all scenarios until all 46 have an
evaluable run. RCA and remediation can have different evaluable denominators,
so state each denominator explicitly.

Use these rules consistently:

- A completed scenario in which the agent never produces a qualifying RCA is
  an RCA failure, not missing data.
- A completed scenario in which no remediation is reached because diagnosis or
  orchestration failed is a remediation failure. This preserves the
  end-to-end nature of the system.
- A remediation that executes but is harmful, penalized, incorrect, or fails
  metric recovery is a remediation failure.
- Mark a scenario non-evaluable only for a predeclared evaluation failure, such
  as corrupt or missing captured inputs, loss of the required metric window,
  or failure of the external judge.
- Report non-evaluable scenarios and reasons separately. Also provide a
  conservative sensitivity result that counts them as failures.

## Secondary results

The two headline rates are intentionally easy to understand, but they should
be accompanied by enough information to show efficiency, quality, and safety:

| Secondary measure | Purpose |
| --- | --- |
| Median RCA rubric score and interquartile range | Shows the quality of RCA outputs beyond root-cause correctness. Calculate one predeclared representative score per run, preferably the earliest qualifying RCA or the final RCA if none qualifies. |
| Median penalized remediation rubric score and interquartile range | Shows remediation quality while retaining deductions for performed harmful actions. Use the earliest qualifying remediation or the final executed remediation if none qualifies. |
| Median attempts to qualifying RCA | Reveals whether success usually requires repeated hypotheses. |
| Median attempts to qualifying remediation | Reveals remediation efficiency and repeated-action behavior. |
| Median time to RCA and time to recovery | Measures operational usefulness, not just eventual correctness. |
| Harmful-action rate | Percentage of evaluated scenarios with at least one applied remediation penalty. Report penalty types and weights. |
| Metric recovery by family | Report improved, stable, worsened, and non-evaluable counts for P95 response time and HTTP 5xx rate separately. |
| Results by application and fault family | Exposes weaknesses hidden by the overall rate, such as node faults versus service CPU, memory, bandwidth, or capacity loss. |

Do not use the maximum RCA or remediation score as the primary summary. A
maximum rewards systems that generate more attempts and can hide poor or unsafe
behavior. A best score may be included only as a clearly labelled
**best-achieved quality** diagnostic.

## Statistical reporting

For each headline proportion, report the numerator, denominator, percentage,
and a 95 percent binomial confidence interval, preferably Wilson's interval.
For continuous secondary measures, report the median and interquartile range;
if comparing systems, use scenario-level paired bootstrap confidence intervals
where the same scenarios are evaluated by both systems.

Avoid significance tests over individual RCA or remediation jobs because jobs
from the same scenario are not independent observations. The scenario or
scenario repetition is the experimental unit.

## Paper-ready results template

Use a compact headline table such as:

| Measure | Successful | Evaluable | Result | 95% CI |
| --- | ---: | ---: | ---: | --- |
| Score-based Scenario Success Rate | `joint score successes` | `graded scenarios` | `SSR%` | `Wilson interval` |
| RCA Scenario Success Rate | `RCA successes` | `RCA-evaluable scenarios` | `RCA-SSR%` | `Wilson interval` |
| Remediation Scenario Recovery Rate | `remediation successes` | `remediation-evaluable scenarios` | `RSRR%` | `Wilson interval` |

Immediately below it, report:

```text
Coverage: evaluated scenarios / 46 planned scenarios
RCA efficiency: median attempts and median time to first qualifying RCA
Recovery efficiency: median attempts and median time to first qualifying remediation
Safety: scenarios with an applied penalty / remediation-evaluable scenarios
```

A suitable methods statement is:

> We treated each fault scenario as the experimental unit. RCA success required
> at least one root-cause-aligned output within the fixed scenario window.
> Remediation success additionally required an aligned executed action, no
> harmful-action penalty, and five-minute recovery without degradation in HTTP
> 5xx rate or response-time P95. We macro-averaged scenario outcomes so that
> scenarios generating more agent attempts did not receive greater weight.

## Recommended interpretation

RCA-SSR answers: **How often did the system eventually identify the correct
production-observable incident condition and affected target?**

RSRR answers: **How often did the complete system safely recover the service
after identifying and acting on the incident?**

Together, these two numbers summarize diagnosis and end-to-end recovery while
remaining interpretable. The accompanying attempt, time, quality, safety, and
fault-family results prevent the headline rates from concealing inefficient or
unsafe behavior.
