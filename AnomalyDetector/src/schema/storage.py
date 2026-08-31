from pydantic import BaseModel


class Metadata(BaseModel):
    namespace: str | None = None
    name: str
    resource: str
    metric: str

    @property
    def key(self):
        scope = self.namespace or "_cluster"
        return f"{scope}:{self.resource}:{self.name}:{self.metric}"


class MetricSeries(BaseModel):
    metadata: Metadata
    timestamps: list[float]
    values: list[float]

    @property
    def latest_timestamp(self) -> float | None:
        if not self.timestamps:
            return None
        return self.timestamps[-1]

    @property
    def latest_value(self) -> float | None:
        if not self.values:
            return None
        return self.values[-1]

    def tail(self, count: int) -> "MetricSeries":
        return MetricSeries(
            metadata=self.metadata,
            timestamps=self.timestamps[-count:],
            values=self.values[-count:],
        )
