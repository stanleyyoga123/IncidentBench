from datetime import datetime, timezone

from pydantic import BaseModel, Field


DETAIL_FIELDS_TO_SURFACE = [
    "anomaly_type",
    "resource",
    "name",
    "metric",
    "timestamp",
    "current_value",
    "baseline_mean",
    "baseline_std",
    "delta_from_baseline",
    "relative_delta_from_baseline",
    "z_score",
    "z_score_threshold",
    "severity",
    "direction",
    "observed_direction",
    "lookback_points",
    "tail_points_evaluated",
    "consecutive_anomalies",
    "metric_semantics",
    "interpretation",
    "rca_hints",
    "remediation_hints",
]


class AnomalyRow(BaseModel):
    id: int
    timestamp: datetime
    resource: str
    name: str
    metrics: str
    method: str
    detail: str

    def detail_fields(self) -> dict[str, str]:
        fields = {}
        for line in self.detail.splitlines():
            key, separator, value = line.partition("=")
            if not separator:
                continue
            fields[key.strip()] = value.strip()
        return fields

    def surfaced_detail_fields(self) -> dict[str, str]:
        parsed = self.detail_fields()
        return {
            key: parsed[key]
            for key in DETAIL_FIELDS_TO_SURFACE
            if key in parsed and parsed[key] != ""
        }

    def to_prompt_section(self) -> str:
        timestamp_utc = self.timestamp.astimezone(timezone.utc).isoformat()
        surfaced = self.surfaced_detail_fields()
        detail_lines = "\n".join(
            f"    {key}: {value}" for key, value in surfaced.items()
        )
        if not detail_lines:
            detail_lines = "    none"

        return (
            f"- Row ID: {self.id}\n"
            f"  Row timestamp: {self.timestamp.isoformat()} ({timestamp_utc})\n"
            f"  Resource: {self.resource}\n"
            f"  Name: {self.name}\n"
            f"  Metric: {self.metrics}\n"
            f"  Method: {self.method}\n"
            "  Parsed detector detail fields:\n"
            f"{detail_lines}\n"
            "  Raw detail:\n"
            f"{self._indented_detail()}"
        )

    def _indented_detail(self) -> str:
        if not self.detail:
            return "    none"
        return "\n".join(f"    {line}" for line in self.detail.splitlines())


class AnomalyRowGroup(BaseModel):
    name: str
    resource: str
    anomalies: list[AnomalyRow] = Field(default_factory=list)

    def to_prompt_section(self) -> str:
        metrics = "\n".join(
            anomaly.to_prompt_section() for anomaly in self.anomalies
        )
        if not metrics:
            metrics = "- none"

        return (
            f"## Group: {self.resource}:{self.name}\n"
            f"Name: {self.name}\n"
            f"Resource: {self.resource}\n\n"
            "Rows:\n"
            f"{metrics}"
        )


class AnomalyBatch(BaseModel):
    anomalies: list[AnomalyRow] = Field(default_factory=list)

    @classmethod
    def from_rows(cls, rows: list[AnomalyRow]) -> "AnomalyBatch":
        return cls(anomalies=rows)

    def grouped_by_name(self) -> list[AnomalyRowGroup]:
        groups: dict[tuple[str, str], AnomalyRowGroup] = {}
        for anomaly in self.anomalies:
            group_key = (anomaly.resource, anomaly.name)
            group = groups.setdefault(
                group_key,
                AnomalyRowGroup(
                    name=anomaly.name,
                    resource=anomaly.resource,
                    anomalies=[],
                ),
            )
            group.anomalies.append(anomaly)

        return sorted(groups.values(), key=lambda group: (group.resource, group.name))

    def row_ids(self) -> list[int]:
        return [anomaly.id for anomaly in self.anomalies]

    def metrics(self) -> list[str]:
        return sorted({anomaly.metrics for anomaly in self.anomalies})

    def to_manager_prompt(self) -> str:
        group_sections = "\n\n".join(
            group.to_prompt_section() for group in self.grouped_by_name()
        )
        if not group_sections:
            group_sections = "- none"

        return (
            "# Detector Anomaly Investigation\n\n"
            "These rows are AnomalyDetector signals from Postgres. Treat them as leads, not proof.\n\n"
            "## Batch Metadata\n"
            f"- Total rows: {len(self.anomalies)}\n"
            f"- Row IDs: {self.row_ids()}\n"
            f"- Metrics present: {self.metrics()}\n"
            "- Default namespace when omitted: online-boutique\n"
            "- Default time window: around the detector timestamp when present, otherwise recent data\n\n"
            "## Notes\n"
            "- Preserve row IDs when referring to evidence.\n"
            "- Use detector detail fields as context and hints, not proof.\n\n"
            "- Treat the detector-named service as the observation point, not as the complete impact boundary; check evidence-connected upstream, downstream, co-located, and same-path services.\n\n"
            "## Grouped Anomalies\n"
            f"{group_sections}\n\n"
            "## Expected Output\n"
            "Return the current orchestrator output fields: `Remediation Required`, `Summary`, `Failed Investigation`, `Evidence`, `Impact Scope`, `Missing Or Uncertain`, and `Remediation Plan`."
        )
