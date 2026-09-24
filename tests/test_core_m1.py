"""Mudanças no núcleo para o M1: entradas por instância, verify_cached, previous_output, force."""

from pathlib import Path

import pytest
from fake_stages import SourceStage, Text, UpperStage
from pydantic import BaseModel

from translaterany.config.loader import ConfigError, load_config
from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import StageRegistry
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class PickOptions(BaseModel):
    source: str = "t_source"


class PickStage(Stage):
    """Lê a etapa indicada nas opções (entradas definidas pela instância)."""

    name = "t_pick"
    version = "1"
    scope = StageScope.EPISODE
    Options = PickOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.inputs = (self.options.source,)

    def run(self, ctx: StageContext) -> None:
        ctx.output.json(Text(text="pick:" + ctx.inputs.json(self.options.source, Text).text))


class ExternalStage(Stage):
    """Simula uma etapa com efeito fora do diretório de dados."""

    name = "t_external"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_source",)
    external_ok = True
    calls: list[str] = []
    seen_previous: list[Path | None] = []
    seen_force: list[bool] = []

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        type(self).seen_previous.append(ctx.previous_output)
        type(self).seen_force.append(ctx.force)
        ctx.output.json(Text(text="ok"))

    def verify_cached(self, ctx: StageContext, artifact_path: Path) -> bool:
        return type(self).external_ok


@pytest.fixture(autouse=True)
def _reset_external() -> None:
    ExternalStage.calls = []
    ExternalStage.seen_previous = []
    ExternalStage.seen_force = []
    ExternalStage.external_ok = True


def _run(data_dir: Path, series_dir: Path, stages: list[Stage], force: bool = False):
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    return Runner(stages, store, FakeLLM()).run(series, episodes, force=force), store, series, episodes


def test_instance_inputs_are_used_by_runner(data_dir: Path, series_dir: Path) -> None:
    summary, store, series, episodes = _run(
        data_dir, series_dir, [SourceStage(), UpperStage(), PickStage(PickOptions(source="t_upper"))]
    )
    assert summary.stages["t_pick"].done == 3
    art = store.artifact_dir(series.key, episodes[0].key) / "t_pick.json"
    assert Text.model_validate_json(art.read_text()).text == "pick:EPISODIO 1"


def test_runner_validates_instance_inputs() -> None:
    with pytest.raises(ValueError, match="t_upper"):
        Runner([SourceStage(), PickStage(PickOptions(source="t_upper"))], ArtifactStore(Path("/x")), FakeLLM())


def test_config_validates_instance_inputs(tmp_path: Path, registry: StageRegistry) -> None:
    registry.register(PickStage)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[pipeline]\nstages = ["t_source", "t_pick"]\n[stages.t_pick.options]\nsource = "t_upper"\n')
    with pytest.raises(ConfigError, match="depende de 't_upper'"):
        load_config(cfg, registry=registry, env={})


def test_translates_defaults_to_false() -> None:
    assert SourceStage.translates is False


def test_verify_cached_false_forces_rerun(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert len(ExternalStage.calls) == 3
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_external"].cached == 3
    ExternalStage.external_ok = False
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_external"].done == 3


def test_previous_output_is_offered_on_rerun(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert ExternalStage.seen_previous == [None, None, None]
    ExternalStage.external_ok = False
    _, store, series, episodes = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    expected = store.artifact_dir(series.key, episodes[0].key) / "t_external.json"
    assert ExternalStage.seen_previous[3] == expected


def test_force_reopens_skipped_and_reaches_context(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("SKIP", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_source"].skipped == 1
    (series_dir / "Season 1" / "S01E01.mkv").write_text("liberado", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_source"].done == 0  # continua pulado sem --force
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()], force=True)
    assert summary.stages["t_source"].done == 1
    assert ExternalStage.seen_force[-1] is True
