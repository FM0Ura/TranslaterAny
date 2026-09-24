import json
from pathlib import Path

import pytest
from fake_stages import CollectStage, SourceStage, UpperStage

from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.reset import reset_from
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.status import series_status
from translaterany.pipeline.units import discover

STAGES = [SourceStage(), UpperStage(), CollectStage()]
ORDER = [s.name for s in STAGES]


def _setup(data_dir: Path, series_dir: Path):
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    Runner(STAGES, store, FakeLLM()).run(series, episodes)
    return store, series, episodes


def test_reset_from_episode_stage_all_episodes(data_dir: Path, series_dir: Path) -> None:
    store, series, episodes = _setup(data_dir, series_dir)
    assert reset_from(store, series, episodes, STAGES, "t_upper") == 4  # 3 episódios + série
    manifest = json.loads(store.manifest_path(series.key, episodes[0].key).read_text())
    assert list(manifest["stages"]) == ["t_source"]
    assert json.loads(store.manifest_path(series.key, None).read_text())["stages"] == {}
    UpperStage.calls.clear()
    summary = Runner(STAGES, store, FakeLLM()).run(series, episodes)
    assert summary.stages["t_upper"].done == 3 and summary.stages["t_source"].cached == 3
    assert summary.stages["t_collect"].done == 1


def test_reset_single_episode(data_dir: Path, series_dir: Path) -> None:
    store, series, episodes = _setup(data_dir, series_dir)
    assert reset_from(store, series, episodes, STAGES, "t_source", episodes[1].key) == 1
    SourceStage.calls.clear()
    summary = Runner(STAGES, store, FakeLLM()).run(series, episodes)
    assert SourceStage.calls == [episodes[1].key]
    assert summary.stages["t_collect"].cached == 1  # artefato idêntico → série continua em cache


def test_reset_reopens_skipped_episode(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("SKIP", encoding="utf-8")
    store, series, episodes = _setup(data_dir, series_dir)
    reset_from(store, series, episodes, STAGES, "t_source", episodes[0].key)
    manifest = json.loads(store.manifest_path(series.key, episodes[0].key).read_text())
    assert manifest["status"] == "ok" and manifest["skip_reason"] is None


def test_reset_errors(data_dir: Path, series_dir: Path) -> None:
    store, series, episodes = _setup(data_dir, series_dir)
    with pytest.raises(ValueError, match="não está no pipeline"):
        reset_from(store, series, episodes, STAGES, "nope")
    with pytest.raises(ValueError, match="etapa de série"):
        reset_from(store, series, episodes, STAGES, "t_collect", episodes[0].key)
    with pytest.raises(ValueError, match="não encontrado"):
        reset_from(store, series, episodes, STAGES, "t_source", "inexistente")


def test_series_status_rows(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E02.mkv").write_text("FAIL", encoding="utf-8")
    (series_dir / "Season 1" / "S01E03.mkv").write_text("SKIP", encoding="utf-8")
    store, series, episodes = _setup(data_dir, series_dir)
    rows = {r.unit: r for r in series_status(store, series.key, ORDER)}
    assert rows["(série)"].last_done == "t_collect"
    assert rows[episodes[0].key].status == "ok" and rows[episodes[0].key].last_done == "t_upper"
    assert rows[episodes[1].key].status == "failed" and "falha simulada" in rows[episodes[1].key].detail
    assert rows[episodes[2].key].status == "skipped" and rows[episodes[2].key].detail == "marcado para pular"


def test_series_status_unknown_series(data_dir: Path) -> None:
    assert series_status(ArtifactStore(data_dir), "nada", ORDER) == []
