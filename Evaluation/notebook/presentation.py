"""Output-only presentation helpers for the evaluation notebook."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from IPython.display import Markdown, display

from evaluation_metrics import EvaluationReport


def show_headline_results(report: EvaluationReport) -> None:
    table = report.headline_df[
        ["measure", "successful", "evaluable", "result_percent", "ci_95_percent", "ci_method"]
    ].copy()
    table.columns = ["Measure", "Successful", "Evaluable", "Result (%)", "95% CI", "CI method"]
    display(table.round(2))
    display(report.coverage_df.round(2))

    chart = report.headline_df
    values = chart["result_percent"].to_numpy(dtype=float)
    lower = values - chart["ci_low_percent"].to_numpy(dtype=float)
    upper = chart["ci_high_percent"].to_numpy(dtype=float) - values
    labels = ["Score-based SSR", "RCA-SSR", "RSRR"]
    colors = ["#4C78A8", "#59A14F", "#F28E2B"]
    fig, axis = plt.subplots(figsize=(9, 4.8))
    bars = axis.bar(labels, values, color=colors, yerr=np.vstack([lower, upper]), capsize=6)
    axis.bar_label(bars, labels=[f"{value:.1f}%" for value in values], padding=5)
    axis.set_ylabel("Scenarios (%)")
    axis.set_ylim(0, max(100, float(np.nanmax(chart["ci_high_percent"])) + 10))
    axis.set_title("Headline scenario-level results with 95% confidence intervals")
    axis.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.show()


def show_scenario_results(report: EvaluationReport) -> None:
    table = report.scenario_df[
        [
            "scenario",
            "application",
            "fault_family",
            "runs",
            "rca_score_threshold_met",
            "remediation_score_threshold_met",
            "score_based_scenario_success",
            "rca_scenario_rate",
            "remediation_scenario_rate",
            "harmful_action_in_any_run",
        ]
    ].copy()
    table["score_based_status"] = np.where(
        table.pop("score_based_scenario_success"), "SUCCESS", "FAILED"
    )
    display(table)


def show_quality_and_safety(report: EvaluationReport) -> None:
    display(report.secondary_df.round(3))
    display(report.safety_df.round(2))
    display(report.metric_outcomes_df)


def show_breakdowns(report: EvaluationReport) -> None:
    display(Markdown("### By application"))
    display(report.application_df.round(2))
    display(Markdown("### By fault family"))
    display(report.fault_family_df.round(2))
    display(Markdown("### By application and fault family"))
    display(report.application_fault_df.round(2))


def show_paper_summary(report: EvaluationReport) -> None:
    display(Markdown(f"> {report.summary_text}"))
    display(
        Markdown(
            "Review non-evaluable counts and conservative coverage-adjusted rates "
            "before using this sentence."
        )
    )
