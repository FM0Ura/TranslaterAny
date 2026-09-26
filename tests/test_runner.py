import json
from pathlib import Path

import pytest
from fake_stages import CollectStage, LengthStage, ReadSeriesStage, SourceStage, Text, UpperOptions, UpperStage

from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.lock import SeriesLock, SeriesLocked
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage, StageScope


def _run(data_dir: Path, series_dir: Path, stages: list[Stage], progress: list | None = None):
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    runner = Runner(
        stages, store, FakeLLM(), on_progress=(lambda *a: progress.append(a)) if progress is not None else None
    )
    return runner.run(series, episodes), store, series, episodes


def _manifest(store: ArtifactStore, series_key: str, episode_key: str | None) -> dict:
    return json.loads(store.manifest_path(series_key, episode_key).read_text())


def test_runs_all_stages_and_writes_artifacts(data_dir: Path, series_dir: Path) -> None:
    summary, store, series, episodes = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert summary.stages["t_source"].done == 3 and summary.stages["t_upper"].done == 3
    assert not summary.failed
    art = store.artifact_dir(series.key, episodes[0].key) / "t_upper.json"
    assert Text.model_validate_json(art.read_text()).text == "EPISODIO 1"
    manifest = _manifest(store, series.key, episodes[0].key)
    assert manifest["stages"]["t_upper"]["status"] == "done"
    assert manifest["stages"]["t_upper"]["artifact_hash"].startswith("sha256:")
    assert json.loads((store.series_dir(series.key) / "series.json").read_text())["name"] == "Minha Série (2020)"


def test_stage_major_order(data_dir: Path, series_dir: Path) -> None:
    progress: list = []
    _run(data_dir, series_dir, [SourceStage(), UpperStage()], progress)
    assert [p[0] for p in progress] == ["t_source"] * 3 + ["t_upper"] * 3
    assert progress[-1] == ("t_upper", 3, 3)


def test_second_run_is_fully_cached(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    SourceStage.calls.clear()
    UpperStage.calls.clear()
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert summary.stages["t_source"].cached == 3 and summary.stages["t_upper"].cached == 3
    assert SourceStage.calls == [] and UpperStage.calls == []


def test_changing_options_reruns_only_that_stage(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), UpperStage(), LengthStage()])
    SourceStage.calls.clear()
    LengthStage.calls.clear()
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), UpperStage(UpperOptions(suffix="!")), LengthStage()])
    assert summary.stages["t_upper"].done == 3
    assert summary.stages["t_source"].cached == 3
    assert summary.stages["t_length"].cached == 3  # não depende de t_upper
    assert SourceStage.calls == [] and LengthStage.calls == []


def test_identical_regenerated_artifact_keeps_downstream_cached(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    UpperStage.calls.clear()

    class SourceV2(SourceStage):
        version = "2"  # invalida t_source, mas o conteúdo gerado é idêntico

    summary, *_ = _run(data_dir, series_dir, [SourceV2(), UpperStage()])
    assert summary.stages["t_source"].done == 3
    assert summary.stages["t_upper"].cached == 3
    assert UpperStage.calls == []


def test_changed_source_file_invalidates(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    (series_dir / "Season 1" / "S01E02.mkv").write_text("mudou", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert summary.stages["t_source"].done == 1 and summary.stages["t_source"].cached == 2
    assert summary.stages["t_upper"].done == 1


def test_tampered_artifact_is_regenerated(data_dir: Path, series_dir: Path) -> None:
    _, store, series, episodes = _run(data_dir, series_dir, [SourceStage()])
    (store.artifact_dir(series.key, episodes[0].key) / "t_source.json").write_text('{"text": "adulterado"}')
    summary, *_ = _run(data_dir, series_dir, [SourceStage()])
    assert summary.stages["t_source"].done == 1


def test_failure_is_isolated_and_retried_next_run(data_dir: Path, series_dir: Path) -> None:
    bad = series_dir / "Season 1" / "S01E02.mkv"
    bad.write_text("FAIL", encoding="utf-8")
    summary, store, series, episodes = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert summary.failed
    assert summary.stages["t_source"].failed == 1 and summary.stages["t_source"].done == 2
    assert summary.stages["t_upper"].done == 2  # episódio com falha não segue
    manifest = _manifest(store, series.key, episodes[1].key)
    assert manifest["status"] == "failed"
    assert "falha simulada" in manifest["stages"]["t_source"]["error"]

    bad.write_text("consertado", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert not summary.failed
    assert summary.stages["t_source"].done == 1 and summary.stages["t_upper"].done == 1


def test_skip_episode_persists(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E03.mkv").write_text("SKIP", encoding="utf-8")
    summary, store, series, episodes = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert summary.stages["t_source"].skipped == 1 and not summary.failed
    assert summary.stages["t_upper"].done == 2
    manifest = _manifest(store, series.key, episodes[2].key)
    assert manifest["status"] == "skipped" and manifest["skip_reason"] == "marcado para pular"
    SourceStage.calls.clear()
    _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert episodes[2].key not in SourceStage.calls  # continua pulado


def test_series_stage_sees_all_episodes_and_episode_stage_reads_it(data_dir: Path, series_dir: Path) -> None:
    stages = [SourceStage(), UpperStage(), CollectStage(), ReadSeriesStage()]
    summary, store, series, episodes = _run(data_dir, series_dir, stages)
    collected = json.loads((store.artifact_dir(series.key, None) / "t_collect.json").read_text())
    assert sorted(collected["items"].values()) == ["EPISODIO 1", "EPISODIO 2", "EPISODIO 3"]
    assert summary.stages["t_read_series"].done == 3
    art = store.artifact_dir(series.key, episodes[0].key) / "t_read_series.json"
    assert Text.model_validate_json(art.read_text()).text == "3"


def test_series_stage_invalidated_when_an_episode_changes(data_dir: Path, series_dir: Path) -> None:
    stages = [SourceStage(), UpperStage(), CollectStage()]
    _run(data_dir, series_dir, stages)
    (series_dir / "Season 1" / "S01E01.mkv").write_text("novo", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, stages)
    assert summary.stages["t_collect"].done == 1


def test_series_stage_failure_stops_following_stages(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("boom", encoding="utf-8")  # t_upper -> "BOOM"
    stages = [SourceStage(), UpperStage(), CollectStage(), ReadSeriesStage()]
    summary, store, series, _ = _run(data_dir, series_dir, stages)
    assert summary.stages["t_collect"].failed == 1
    assert summary.stages["t_read_series"].done == 0
    assert _manifest(store, series.key, None)["status"] == "failed"


def test_interrupt_then_resume(data_dir: Path, series_dir: Path) -> None:
    third = series_dir / "Season 1" / "S01E03.mkv"
    third.write_text("INTERRUPT", encoding="utf-8")
    with pytest.raises(KeyboardInterrupt):
        _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    assert not store.manifest_path(series.key, episodes[2].key).exists()

    third.write_text("episodio 3", encoding="utf-8")
    SourceStage.calls.clear()
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    assert SourceStage.calls == [episodes[2].key]
    assert summary.stages["t_source"].cached == 2 and summary.stages["t_upper"].done == 3


def test_lock_held_by_other_run(data_dir: Path, series_dir: Path) -> None:
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    with SeriesLock(store.lock_path(series.key)):
        with pytest.raises(SeriesLocked):
            Runner([SourceStage()], store, FakeLLM()).run(series, episodes)


def test_leftover_tmp_files_are_cleaned(data_dir: Path, series_dir: Path) -> None:
    _, store, series, episodes = _run(data_dir, series_dir, [SourceStage()])
    leftover = store.artifact_dir(series.key, episodes[0].key) / "t_source.json.tmp-999999"
    leftover.write_text("parcial")
    _run(data_dir, series_dir, [SourceStage()])
    assert not leftover.exists()


def test_stage_without_output_fails(data_dir: Path, series_dir: Path) -> None:
    class Silent(SourceStage):
        name = "t_silent"

        def run(self, ctx) -> None:
            pass

    summary, *_ = _run(data_dir, series_dir, [Silent()])
    assert summary.stages["t_silent"].failed == 3


def test_undeclared_input_read_fails(data_dir: Path, series_dir: Path) -> None:
    class Sneaky(UpperStage):
        name = "t_sneaky"
        inputs = ()

    summary, *_ = _run(data_dir, series_dir, [SourceStage(), Sneaky()])
    assert summary.stages["t_sneaky"].failed == 3


def test_runner_rejects_dependency_out_of_order() -> None:
    with pytest.raises(ValueError, match="não vem antes"):
        Runner([UpperStage(), SourceStage()], ArtifactStore(Path("/nao/usado")), FakeLLM())


def test_removed_episode_drops_out_of_series_stage(data_dir: Path, series_dir: Path) -> None:
    stages = [SourceStage(), UpperStage(), CollectStage()]
    _run(data_dir, series_dir, stages)
    (series_dir / "Season 1" / "S01E03.mkv").unlink()
    summary, store, series, _ = _run(data_dir, series_dir, stages)
    assert summary.stages["t_collect"].done == 1
    collected = json.loads((store.artifact_dir(series.key, None) / "t_collect.json").read_text())
    assert len(collected["items"]) == 2


def test_skip_episode_in_series_stage_marks_series_failed(data_dir: Path, series_dir: Path) -> None:
    class SkippingCollect(CollectStage):
        name = "t_skipping_collect"

        def run(self, ctx) -> None:
            from translaterany.pipeline.stage import SkipEpisode

            raise SkipEpisode("não faz sentido aqui")

    summary, store, series, _ = _run(data_dir, series_dir, [SourceStage(), UpperStage(), SkippingCollect()])
    assert summary.stages["t_skipping_collect"].failed == 1
    manifest = _manifest(store, series.key, None)
    assert manifest["status"] == "failed"
    assert "SkipEpisode não é permitido" in manifest["stages"]["t_skipping_collect"]["error"]


def test_unreadable_source_is_isolated(data_dir: Path, series_dir: Path) -> None:
    bad = series_dir / "Season 1" / "S01E02.mkv"
    bad.chmod(0)
    try:
        summary, store, series, episodes = _run(data_dir, series_dir, [SourceStage(), UpperStage()])
    finally:
        bad.chmod(0o644)
    assert summary.stages["t_source"].done == 2 and summary.stages["t_source"].failed == 1
    assert summary.stages["t_upper"].done == 2
    manifest = _manifest(store, series.key, episodes[1].key)
    assert manifest["status"] == "failed"
    assert "PermissionError" in manifest["stages"]["t_source"]["error"]


def test_series_stage_key_tracks_episode_set(data_dir: Path, series_dir: Path) -> None:
    class CountStage(Stage):
        name = "t_count"
        version = "1"
        scope = StageScope.SERIES

        def run(self, ctx) -> None:
            ctx.output.json(Text(text=str(len(ctx.episodes))))

    _run(data_dir, series_dir, [CountStage()])
    (series_dir / "Season 1" / "S01E04.mkv").write_text("episodio 4", encoding="utf-8")
    summary, store, series, _ = _run(data_dir, series_dir, [CountStage()])
    assert summary.stages["t_count"].done == 1
    art = store.artifact_dir(series.key, None) / "t_count.json"
    assert Text.model_validate_json(art.read_text()).text == "4"


def test_runner_rejects_reads_source_on_series_stage() -> None:
    class SeriesSource(CollectStage):
        name = "t_series_source"
        inputs = ()
        reads_source = True

    with pytest.raises(ValueError, match="reads_source"):
        Runner([SeriesSource()], ArtifactStore(Path("/nao/usado")), FakeLLM())
