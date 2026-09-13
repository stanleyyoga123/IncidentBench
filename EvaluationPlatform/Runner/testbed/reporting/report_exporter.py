from pathlib import Path


class ReportExporter:
    def export(self, output_dir: Path, summary, comparison) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "chaos-step-summary.csv"
        comparison_path = output_dir / "chaos-step-agent-comparison.csv"
        summary.to_csv(summary_path, index=False)
        comparison.to_csv(comparison_path, index=False)
        return {"summary": summary_path, "comparison": comparison_path}
