"""Agregação do `report`: manifests (camada 1) + metrics.json (camada 2). Sem texto de legenda."""

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from translaterany.checks.metrics import HISTOGRAM_BINS, EpisodeMetrics, ReadingSpeedStats, SeverityCounts
from translaterany.checks.snapshots import histogram_percentile
from translaterany.llm.metered import LLMStats, ModelStats
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import StageRecord

REPORT_SCHEMA = 1
METRICS_STAGE = "quality_checks"


class MetricsError(Exception):
    """metrics.json ilegível ou de schema desconhecido."""


class StageSummary(BaseModel):
    units_done: int = 0
    units_failed: int = 0
    duration_s: float = 0.0
    llm: LLMStats = Field(default_factory=LLMStats)
    counters: dict[str, int] = Field(default_factory=dict)

    @property
    def mean_duration_s(self) -> float:
        runs = self.units_done + self.units_failed
        return self.duration_s / runs if runs else 0.0


class CheckSummary(BaseModel):
    counts: SeverityCounts = Field(default_factory=SeverityCounts)
    rate: float = 0.0


class SnapshotSummary(BaseModel):
    episodes: int = 0
    changed: int = 0
    new: int = 0
    resolved: int = 0
    edit_ratio_mean: float = 0.0


class EpisodeRank(BaseModel):
    episode: str
    lines: int
    error_lines: int
    error_rate: float


class SeriesReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_version: int = Field(default=REPORT_SCHEMA, alias="schema")
    series: str
    generated_at: datetime = Field(default_factory=datetime.now)
    episodes: int = 0
    lines: int = 0
    stages: dict[str, StageSummary] = Field(default_factory=dict)
    models: dict[str, ModelStats] = Field(default_factory=dict)
    final_checks: dict[str, CheckSummary] = Field(default_factory=dict)
    reading_speed: ReadingSpeedStats = Field(default_factory=ReadingSpeedStats)
    snapshots: dict[str, SnapshotSummary] = Field(default_factory=dict)
    worst_episodes: list[EpisodeRank] = Field(default_factory=list)
    missing_metrics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def load_episode_metrics(store: ArtifactStore, series_key: str, episode_key: str) -> EpisodeMetrics | None:
    manifest = store.read_manifest(series_key, episode_key)
    record = manifest.stages.get(METRICS_STAGE) if manifest else None
    if record is None or record.status != "done" or record.artifact is None:
        return None
    path = store.artifact_dir(series_key, episode_key) / record.artifact
    try:
        metrics = EpisodeMetrics.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, UnicodeDecodeError) as exc:
        raise MetricsError(f"metrics.json ilegível em {episode_key}: {type(exc).__name__}") from exc
    if metrics.schema_version != 1:
        raise MetricsError(f"metrics.json de {episode_key} tem schema {metrics.schema_version} desconhecido")
    return metrics


def _add_stage(summary: StageSummary, record: StageRecord) -> None:
    if record.status == "done":
        summary.units_done += 1
    else:
        summary.units_failed += 1
    summary.duration_s += record.duration_s
    if record.llm is not None:
        summary.llm.add(record.llm)
    for name, n in record.counters.items():
        summary.counters[name] = summary.counters.get(name, 0) + n


def build_report(
    store: ArtifactStore,
    series_key: str,
    series_name: str,
    stage_order: Sequence[str],
    episodes: Sequence[str] | None = None,
) -> SeriesReport:
    report = SeriesReport(series=series_name)
    keys = list(episodes) if episodes is not None else store.episode_keys(series_key)
    manifests = [store.read_manifest(series_key, None)] if episodes is None else []
    manifests += [store.read_manifest(series_key, k) for k in keys]
    stage_names: dict[str, None] = dict.fromkeys(stage_order)
    for manifest in manifests:
        if manifest is None:
            continue
        for name, record in manifest.stages.items():
            stage_names.setdefault(name, None)
            _add_stage(report.stages.setdefault(name, StageSummary()), record)
    report.stages = {n: report.stages[n] for n in stage_names if n in report.stages}
    for summary in report.stages.values():
        for model_id, stats in summary.llm.by_model.items():
            report.models.setdefault(model_id, ModelStats()).add(stats)

    report.episodes = len(keys)
    hist = [0] * HISTOGRAM_BINS
    edit_sums: dict[str, float] = {}
    for key in keys:
        try:
            metrics = load_episode_metrics(store, series_key, key)
        except MetricsError as exc:
            report.warnings.append(str(exc))
            metrics = None
        if metrics is None:
            report.missing_metrics.append(key)
            continue
        final = metrics.final
        report.lines += final.lines
        for check, counts in final.checks.items():
            report.final_checks.setdefault(check, CheckSummary()).counts.add(counts)
        rs = final.reading_speed
        report.reading_speed.over_limit += rs.over_limit
        report.reading_speed.cps_max = max(report.reading_speed.cps_max, rs.cps_max)
        hist = [a + b for a, b in zip(hist, rs.cps_histogram, strict=False)]
        for snap in metrics.snapshots:
            s = report.snapshots.setdefault(snap.stage, SnapshotSummary())
            s.episodes += 1
            s.changed += snap.delta.changed
            s.new += snap.delta.new
            s.resolved += snap.delta.resolved
            edit_sums[snap.stage] = edit_sums.get(snap.stage, 0.0) + snap.delta.edit_ratio
        if final.lines:
            report.worst_episodes.append(
                EpisodeRank(
                    episode=key,
                    lines=final.lines,
                    error_lines=final.flagged_lines.error,
                    error_rate=round(final.flagged_lines.error / final.lines, 4),
                )
            )
    for check in report.final_checks.values():
        check.rate = round((check.counts.warn + check.counts.error) / report.lines, 4) if report.lines else 0.0
    for stage, s in report.snapshots.items():
        s.edit_ratio_mean = round(edit_sums[stage] / s.episodes, 4) if s.episodes else 0.0
    report.reading_speed.cps_histogram = hist
    report.reading_speed.cps_p50 = histogram_percentile(hist, 0.5)
    report.reading_speed.cps_p95 = histogram_percentile(hist, 0.95)
    report.worst_episodes = sorted(report.worst_episodes, key=lambda r: r.error_rate, reverse=True)[:5]
    return report


class DeltaRow(BaseModel):
    metric: str
    current: float
    baseline: float

    @property
    def delta(self) -> float:
        return self.current - self.baseline


def compare_reports(current: SeriesReport, baseline: SeriesReport) -> list[DeltaRow]:
    """Deltas de indicadores e custos. Em todos, valor menor é melhor."""
    rows: list[DeltaRow] = []
    for check in sorted(set(current.final_checks) | set(baseline.final_checks)):
        cur, base = current.final_checks.get(check, CheckSummary()), baseline.final_checks.get(check, CheckSummary())
        rows.append(DeltaRow(metric=f"final.{check}.rate", current=cur.rate, baseline=base.rate))
    rows.append(
        DeltaRow(
            metric="reading_speed.cps_p95",
            current=current.reading_speed.cps_p95,
            baseline=baseline.reading_speed.cps_p95,
        )
    )
    for stage in [s for s in current.stages if s in baseline.stages]:
        cur, base = current.stages[stage], baseline.stages[stage]
        rows.append(DeltaRow(metric=f"stage.{stage}.mean_duration_s", current=cur.mean_duration_s,
                             baseline=base.mean_duration_s))  # fmt: skip
        rows.append(DeltaRow(metric=f"stage.{stage}.output_tokens", current=cur.llm.output_tokens,
                             baseline=base.llm.output_tokens))  # fmt: skip
        rows.append(DeltaRow(metric=f"stage.{stage}.cost_usd", current=cur.llm.cost_usd, baseline=base.llm.cost_usd))
    return rows
