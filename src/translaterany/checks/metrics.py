"""Formato do metrics.json (camada 2) gravado pela etapa quality_checks."""

from pydantic import BaseModel, ConfigDict, Field

from translaterany.checks.models import Finding

METRICS_SCHEMA = 1
HISTOGRAM_BINS = 41  # faixas de 1 CPS: [0,1) ... [39,40), [40, ∞)


class SeverityCounts(BaseModel):
    info: int = 0
    warn: int = 0
    error: int = 0

    def add(self, other: SeverityCounts) -> None:
        self.info += other.info
        self.warn += other.warn
        self.error += other.error


class SnapshotDelta(BaseModel):
    changed: int = 0
    edit_ratio: float = 0.0
    new: int = 0
    resolved: int = 0


class SnapshotMetrics(BaseModel):
    stage: str
    lines: int = 0
    checks: dict[str, SeverityCounts] = Field(default_factory=dict)
    delta: SnapshotDelta = Field(default_factory=SnapshotDelta)


class ReadingSpeedStats(BaseModel):
    cps_p50: float = 0.0
    cps_p95: float = 0.0
    cps_max: float = 0.0
    over_limit: int = 0
    cps_histogram: list[int] = Field(default_factory=lambda: [0] * HISTOGRAM_BINS)


class FinalMetrics(BaseModel):
    lines: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    checks: dict[str, SeverityCounts] = Field(default_factory=dict)
    flagged_lines: SeverityCounts = Field(default_factory=SeverityCounts)
    reading_speed: ReadingSpeedStats = Field(default_factory=ReadingSpeedStats)
    findings: list[Finding] = Field(default_factory=list)


class EpisodeMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)  # grava "schema", como o manifest

    schema_version: int = Field(default=METRICS_SCHEMA, alias="schema")
    snapshots: list[SnapshotMetrics] = Field(default_factory=list)
    final: FinalMetrics = Field(default_factory=FinalMetrics)
    episode_checks: list[Finding] = Field(default_factory=list)
