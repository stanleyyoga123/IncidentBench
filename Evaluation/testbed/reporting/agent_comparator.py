import numpy as np
import pandas as pd


class AgentComparator:
    METRICS = [
        "avg_cpu_cores",
        "avg_response_ms",
        "avg_p95_ms",
        "peak_p95_ms",
        "avg_rps",
        "avg_5xx_rps",
        "failure_pct",
        "avg_instances",
    ]
    LOWER_IS_BETTER = {
        "avg_cpu_cores",
        "avg_response_ms",
        "avg_p95_ms",
        "peak_p95_ms",
        "avg_5xx_rps",
        "failure_pct",
    }

    def compare(self, summary: pd.DataFrame) -> pd.DataFrame:
        if summary.empty:
            return pd.DataFrame()
        keys = [
            "scenario",
            "placement",
            "placement_fingerprint",
            "step_index",
            "step_name",
            "chaos",
        ]
        working = summary.copy()
        if "placement" not in working:
            working["placement"] = "unmanaged"
        if "placement_fingerprint" not in working:
            working["placement_fingerprint"] = "unknown"
        presence = working.assign(_present=1).pivot_table(
            index=keys,
            columns="mode",
            values="_present",
            aggfunc="sum",
            fill_value=0,
        )
        if "agent" not in presence or "non-agent" not in presence:
            return pd.DataFrame()
        eligible = presence.index[
            (presence["agent"] > 0) & (presence["non-agent"] > 0)
        ]
        if eligible.empty:
            return pd.DataFrame()
        result = working.pivot_table(
            index=keys,
            columns="mode",
            values=self.METRICS,
            aggfunc="mean",
        )
        result = result.loc[result.index.isin(eligible)]
        if result.empty:
            return pd.DataFrame()
        result.columns = [f"{metric}_{mode}" for metric, mode in result.columns]
        result = result.reset_index()
        for metric in self.METRICS:
            agent, non_agent = f"{metric}_agent", f"{metric}_non-agent"
            if agent not in result or non_agent not in result:
                continue
            denominator = result[non_agent].replace(0, np.nan)
            delta = result[non_agent] - result[agent]
            if metric not in self.LOWER_IS_BETTER:
                delta = -delta
            result[f"{metric}_improvement_pct"] = 100 * delta / denominator
        return result
