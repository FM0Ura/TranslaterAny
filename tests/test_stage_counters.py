"""Contadores das etapas (M5) e episódio correto na TM (correção do M4)."""

from pathlib import Path

from mkvtools import needs_mkvtoolnix

from translaterany.library import discover
from translaterany.llm.client import LLMOutputError
from translaterany.llm.fake import FakeLLM
from translaterany.memory.tm import TranslationMemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.translator import DialogueBatchTranslator, TranslationBatch, TranslationItem

UP_TO_REDISTRIBUTE = DEFAULT_PIPELINE[: DEFAULT_PIPELINE.index("redistribute_sentences") + 1]


def test_translator_counts_fallback_split_and_reconcile() -> None:
    metrics = StageMetrics()
    lines = [DialogueLine(id="a", text="One"), DialogueLine(id="b", text="Two")]

    def script(req):
        if "[a]" in req.prompt and "[b]" in req.prompt:
            return TranslationBatch(items=[TranslationItem(id="a", text="Um")])  # b faltando
        raise LLMOutputError("sem saída")  # pedido só de b falha

    tr = DialogueBatchTranslator(FakeLLM(script), max_context_lines=0, metrics=metrics)
    result = tr.translate_lines(lines)
    assert result == {"a": "Um", "b": "Two"}
    assert metrics.counters["ids_reconciled"] == 1
    assert metrics.counters["fallback_original"] == 1


def test_translator_counts_batches_split() -> None:
    metrics = StageMetrics()
    lines = [DialogueLine(id="a", text="One"), DialogueLine(id="b", text="Two")]
    calls = {"n": 0}

    def script(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return TranslationBatch(items=[])  # tudo faltando: bisseção
        line_id = "a" if "[a]" in req.prompt else "b"
        return TranslationBatch(items=[TranslationItem(id=line_id, text=line_id.upper())])

    DialogueBatchTranslator(FakeLLM(script), max_context_lines=0, metrics=metrics).translate_lines(lines)
    assert metrics.counters["batches_split"] == 1


@needs_mkvtoolnix
def test_counters_recorded_and_tm_episode(tmp_path: Path, synthetic_series: Path) -> None:
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(synthetic_series)
    stages = [
        MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
        for n in UP_TO_REDISTRIBUTE
    ]
    llm = FakeLLM(
        responses={"Where are we going, friend?": "Aonde vamos, amigo?", "Estação Central": "Estação Central!"}
    )
    summary = Runner(stages, store, llm).run(series, episodes)
    assert not summary.failed
    manifest = store.load_manifest(series, episodes[0])
    assert manifest.stages["translate_dialogue"].counters["lines"] >= 1
    assert "tm_candidates" in manifest.stages["translation_memory"].counters
    assert "merged_groups" in manifest.stages["merge_sentences"].counters
    assert manifest.stages["translate_dialogue"].llm is not None
    tm = TranslationMemoryStore(store.series_dir(series.key) / "memory" / "translation_memory.yaml")
    entries = tm.load().entries.values()
    assert any(episodes[0].key in e.episodes for e in entries)  # antes: episódio vazio (bug episode.id)
