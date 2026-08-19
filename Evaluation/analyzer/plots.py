from pathlib import Path

import pandas as pd

from testbed.reporting.prometheus_metric_reader import PrometheusMetricReader

from .log import progress
from .timebase import elapsed_minutes


def plot_run(run_folder: Path, origin: float, output_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    reader = PrometheusMetricReader()
    metric_files = _metric_files(run_folder)
    progress(f"plotting {len(metric_files)} metric file(s)")
    for index, metric_path in enumerate(metric_files, start=1):
        frame = reader.read_all(run_folder, metric_path.stem)
        if frame.empty:
            continue
        frame = frame.copy()
        frame["elapsed_minutes"] = frame["timestamp"].map(lambda ts: elapsed_minutes(ts, origin))
        figure, axes = plt.subplots(figsize=(11, 5))
        for name, series in frame.groupby("name"):
            ordered = series.sort_values("elapsed_minutes")
            axes.plot(ordered["elapsed_minutes"], ordered["value"], label=str(name), linewidth=1.2)
        axes.axvline(0, color="black", linestyle="--", linewidth=1, label="chaos start")
        axes.set_xlabel("elapsed minutes (0 = chaos start)")
        axes.set_ylabel(metric_path.stem)
        axes.set_title(metric_path.stem)
        if frame["name"].nunique() <= 16:
            axes.legend(fontsize=7, loc="best")
        figure.tight_layout()
        destination = output_dir / f"{metric_path.stem}.png"
        figure.savefig(destination, dpi=120)
        plt.close(figure)
        written.append(destination)
        progress(f"plot {index}/{len(metric_files)}: {metric_path.stem}")
    locust = _plot_locust(run_folder, origin, output_dir, plt)
    if locust is not None:
        written.append(locust)
    return written


def _metric_files(run_folder: Path) -> list[Path]:
    folder = Path(run_folder) / "metrics"
    if not folder.is_dir():
        return []
    return sorted(
        path
        for path in folder.glob("*.json")
        if path.name != "metrics.json"
    )


def _plot_locust(run_folder: Path, origin: float, output_dir: Path, plt) -> Path | None:
    paths = sorted((Path(run_folder) / "loadgenerator").glob("*_stats_history.csv"))
    if not paths:
        return None
    history = pd.read_csv(paths[0], low_memory=False)
    if "Name" not in history.columns or "Timestamp" not in history.columns:
        return None
    history = history[history["Name"].astype(str) == "Aggregated"].copy()
    history["Timestamp"] = pd.to_numeric(history["Timestamp"], errors="coerce")
    history = history.dropna(subset=["Timestamp"])
    if history.empty:
        return None
    history["elapsed_minutes"] = history["Timestamp"].map(lambda ts: elapsed_minutes(float(ts), origin))
    figure, axes = plt.subplots(figsize=(11, 5))
    plotted = False
    for column, label in (
        ("Requests/s", "requests/s"),
        ("Failures/s", "failures/s"),
        ("Total Average Response Time", "avg response ms"),
    ):
        if column in history.columns:
            values = pd.to_numeric(history[column], errors="coerce")
            if values.notna().any():
                axes.plot(history["elapsed_minutes"], values, label=label, linewidth=1.2)
                plotted = True
    if not plotted:
        plt.close(figure)
        return None
    axes.axvline(0, color="black", linestyle="--", linewidth=1, label="chaos start")
    axes.set_xlabel("elapsed minutes (0 = chaos start)")
    axes.set_ylabel("locust")
    axes.set_title("locust_aggregated")
    axes.legend(fontsize=8)
    figure.tight_layout()
    destination = output_dir / "locust_aggregated.png"
    figure.savefig(destination, dpi=120)
    plt.close(figure)
    return destination
