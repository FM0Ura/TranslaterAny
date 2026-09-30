# tests/test_report.py
"""Agregação do report (M5): manifests + metrics.json -> SeriesReport."""

from pathlib import Path

import pytest

from translaterany.checks import Finding
from translaterany.checks.metrics import (
    EpisodeMetrics,
    FinalMetrics,
    ReadingSpeedStats,
    SeverityCounts,
    SnapshotDelta,
    SnapshotMetrics,
)
from translaterany.llm.metered import LLMStats, ModelStats
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import Manifest, StageRecord, UnitInfo, save_manifest
from translaterany.pipeline.report import SeriesReport, build_report, compare_reports

SERIES = "show"


def write_episode(store: ArtifactStore, ep: str, *, metrics: EpisodeMetrics | None, cost: float = 0.5,
                  corrupt: bool = False, series: str = SERIES) -> None:  # fmt: skip
    llm = LLMStats(calls=2, errors={"output": 1},
                   by_model={"fake:t": ModelStats(calls=2, input_tokens=100, output_tokens=50,
                                                  cost_usd=cost)})  # fmt: skip
    stages = {"translate_dialogue": StageRecord(status="done", duration_s=10.0, llm=llm, counters={"lines": 5})}
    if metrics is not None or corrupt:
        stages["quality_checks"] = StageRecord(status="done", artifact="quality_checks.json")
    save_manifest(store.manifest_path(series, ep), Manifest(unit=UnitInfo(series=series, episode=ep), stages=stages))
    path = store.artifact_dir(series, ep) / "quality_checks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        path.write_text("{nao é json", encoding="utf-8")
    elif metrics is not None:
        path.write_text(metrics.model_dump_json(by_alias=True), encoding="utf-8")


def metrics(lines: int, errors: int, hist_bin: int) -> EpisodeMetrics:
    hist = [0] * 41
    hist[hist_bin] = lines
    findings = [Finding(check="reading_speed", unit_id=f"u{i}", severity="error", message="CPS") for i in range(errors)]
    return EpisodeMetrics(
        snapshots=[SnapshotMetrics(stage="translate_dialogue", lines=lines,
                                   delta=SnapshotDelta(changed=lines, edit_ratio=0.2, new=errors))],
        final=FinalMetrics(lines=lines, by_type={"dialogue": lines},
                           checks={"reading_speed": SeverityCounts(error=errors)},
                           flagged_lines=SeverityCounts(error=errors),
                           reading_speed=ReadingSpeedStats(over_limit=errors, cps_max=float(hist_bin),
                                                           cps_histogram=hist),
                           findings=findings),
    )  # fmt: skip


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    s = ArtifactStore(tmp_path / "data")
    write_episode(s, "S01E01", metrics=metrics(10, 1, 12))
    write_episode(s, "S01E02", metrics=metrics(10, 4, 18))
    write_episode(s, "S01E03", metrics=None)
    write_episode(s, "S01E04", metrics=None, corrupt=True)
    return s


def test_build_report_aggregates(store: ArtifactStore) -> None:
    report = build_report(store, SERIES, "Show", ["translate_dialogue", "quality_checks"])
    td = report.stages["translate_dialogue"]
    assert td.units_done == 4 and td.duration_s == 40.0 and td.mean_duration_s == 10.0
    assert td.llm.calls == 8 and td.llm.errors == {"output": 4} and td.counters == {"lines": 20}
    assert report.models["fake:t"].cost_usd == pytest.approx(2.0)
    assert report.lines == 20 and report.episodes == 4
    assert report.final_checks["reading_speed"].counts.error == 5
    assert report.final_checks["reading_speed"].rate == pytest.approx(5 / 20)
    assert report.reading_speed.over_limit == 5 and report.reading_speed.cps_max == 18.0
    assert report.reading_speed.cps_p50 == 13.0  # metade das linhas na faixa [12,13)
    assert report.snapshots["translate_dialogue"].new == 5
    assert report.snapshots["translate_dialogue"].edit_ratio_mean == pytest.approx(0.2)
    assert [r.episode for r in report.worst_episodes] == ["S01E02", "S01E01"]
    assert report.missing_metrics == ["S01E03", "S01E04"]
    assert any("S01E04" in w for w in report.warnings)


def test_report_has_no_subtitle_text(store: ArtifactStore) -> None:
    raw = build_report(store, SERIES, "Show", []).model_dump_json(by_alias=True)
    assert "findings" not in raw and "excerpt" not in raw


def test_episode_filter(store: ArtifactStore) -> None:
    report = build_report(store, SERIES, "Show", [], episodes=["S01E02"])
    assert report.episodes == 1 and report.lines == 10


def test_json_roundtrip_and_compare(store: ArtifactStore, tmp_path: Path) -> None:
    current = build_report(store, SERIES, "Show", ["translate_dialogue"])
    saved = tmp_path / "base.json"
    saved.write_text(current.model_dump_json(by_alias=True), encoding="utf-8")
    baseline = SeriesReport.model_validate_json(saved.read_text(encoding="utf-8"))
    rows = {r.metric: r for r in compare_reports(current, baseline)}
    assert rows["final.reading_speed.rate"].delta == 0
    baseline.final_checks["reading_speed"].rate = 0.5
    rows = {r.metric: r for r in compare_reports(current, baseline)}
    assert rows["final.reading_speed.rate"].delta == pytest.approx(0.25 - 0.5)
    assert "stage.translate_dialogue.cost_usd" in rows


def test_rate_counts_affected_lines_not_findings(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "data")
    m = metrics(10, 0, 12)
    m.final.findings = [Finding(check="reading_speed", unit_id="u1", severity="error", message=x) for x in "abc"]
    m.final.findings.append(Finding(check="reading_speed", unit_id="u1", severity="warn", message="d"))
    m.final.checks = {"reading_speed": SeverityCounts(error=3, warn=1)}
    m.final.lines_by_check = {"reading_speed": SeverityCounts(error=1, warn=1)}
    write_episode(store, "S01E01", metrics=m)
    cs = build_report(store, SERIES, "Show", ["quality_checks"]).final_checks["reading_speed"]
    assert cs.counts.error == 3 and cs.affected_lines == 1 and cs.lines.error == 1
    assert cs.rate == pytest.approx(0.1) and cs.rate <= 1
