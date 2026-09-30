"""Runner grava uso da IA e contadores no StageRecord (M5)."""

import json
from pathlib import Path

from fake_stages import SourceStage, Text
from pydantic import BaseModel

from translaterany.library import discover
from translaterany.llm.client import LLMRequest
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import MANIFEST_SCHEMA, UnitInfo, load_manifest
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class Out(BaseModel):
    text: str = "ok"


class AskStage(Stage):
    """Chama a IA uma vez, conta uma linha; falha se o texto da origem pedir."""

    name = "t_ask"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_source",)

    def run(self, ctx: StageContext) -> None:
        text = ctx.inputs.json("t_source", Text).text
        ctx.llm.generate(LLMRequest(model="translate", instructions="i" * 40, prompt="p" * 40, output_type=Out))
        ctx.metrics.count("lines", 2)
        if "BOOM" in text:
            raise RuntimeError("falhou depois de chamar a IA")
        ctx.output.json(Text(text=text))


def _run(data_dir: Path, root: Path, llm: FakeLLM):
    store = ArtifactStore(data_dir)
    series, episodes = discover(root)
    runner = Runner([SourceStage(), AskStage()], store, llm, prices=lambda alias: (1.0, 1.0))
    return runner.run(series, episodes), store, series, episodes


def test_record_has_llm_and_counters(data_dir: Path, series_dir: Path) -> None:
    _, store, series, episodes = _run(data_dir, series_dir, FakeLLM(lambda r: Out()))
    record = store.load_manifest(series, episodes[0]).stages["t_ask"]
    assert record.llm is not None and record.llm.calls == 1
    assert record.llm.by_model["fake:translate"].cost_usd > 0
    assert record.counters == {"lines": 2}
    assert store.load_manifest(series, episodes[0]).stages["t_source"].llm is None  # não chamou IA


def test_cache_hit_keeps_original_numbers(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, FakeLLM(lambda r: Out()))
    summary, store, series, episodes = _run(data_dir, series_dir, FakeLLM())  # sem provedor: não pode ser chamado
    assert summary.stages["t_ask"].cached == 3
    assert store.load_manifest(series, episodes[0]).stages["t_ask"].llm.calls == 1


def test_failed_record_keeps_partial_stats(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("BOOM", encoding="utf-8")
    _, store, series, episodes = _run(data_dir, series_dir, FakeLLM(lambda r: Out()))
    record = store.load_manifest(series, episodes[0]).stages["t_ask"]
    assert record.status == "failed"
    assert record.llm.calls == 1 and record.counters == {"lines": 2}


def test_schema_1_manifest_is_read_and_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"schema": 1, "unit": {"series": "s"}, "stages": {"a": {"status": "done", "key": "k"}}}),
        encoding="utf-8",
    )
    manifest = load_manifest(path, UnitInfo(series="s"))
    assert manifest.stages["a"].llm is None and manifest.stages["a"].counters == {}
    from translaterany.pipeline.manifest import save_manifest

    save_manifest(path, manifest)
    assert json.loads(path.read_text())["schema"] == MANIFEST_SCHEMA == 2
