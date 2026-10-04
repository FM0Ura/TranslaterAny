"""Etapas normalize, classify, write e publish com MKVs sintéticos."""

import json
from pathlib import Path

from mkvtools import needs_mkvtoolnix
from pipeline_helpers import artifact, run_stages

from translaterany.pipeline.stage import Stage
from translaterany.stages.classify import ClassifyStage
from translaterany.stages.extract import ExtractStage
from translaterany.stages.normalize import NormalizeStage
from translaterany.stages.publish import PublishStage
from translaterany.stages.select_track import SelectTrackStage
from translaterany.stages.write import WriteOptions, WriteStage

pytestmark = needs_mkvtoolnix


def _stages(translate: bool = False) -> list[Stage]:
    from fake_stages import TranslateStage

    stages: list[Stage] = [SelectTrackStage(), ExtractStage(), NormalizeStage(), ClassifyStage()]
    if translate:
        stages.append(TranslateStage())
    stages.append(WriteStage(WriteOptions(text_source="t_translate" if translate else "normalize")))
    stages.append(PublishStage())
    return stages


def test_pipeline_without_translation_is_identity(data_dir: Path, synthetic_series: Path) -> None:
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages())
    assert not summary.failed
    extracted = artifact(store, s, eps[0], "extract.ass").read_bytes()
    assert artifact(store, s, eps[0], "write.ass").read_bytes() == extracted
    publish = json.loads(artifact(store, s, eps[0], "publish.json").read_text())
    assert publish == {"published": False, "reason": "pipeline sem tradução", "path": None, "sha256": None}
    assert not list(synthetic_series.rglob("*.pt-BR.ass"))
    classify = json.loads(artifact(store, s, eps[0], "classify.json").read_text())
    assert classify["counts"] == {"dialogue": 2, "sign": 1}


def test_translation_is_published_next_to_video(data_dir: Path, synthetic_series: Path) -> None:
    _, store, s, eps = run_stages(data_dir, synthetic_series, _stages(translate=True))
    published = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    text = published.read_text(encoding="utf-8")
    assert "; TranslaterAny" in text
    assert "WHERE ARE WE GOING, FRIEND?" in text
    assert "TO THE {\\i1}OLD{\\i0} STATION." in text
    assert "{\\pos(101,100)}ESTAÇÃO CENTRAL" in text


def test_deleted_publication_is_restored(data_dir: Path, synthetic_series: Path) -> None:
    run_stages(data_dir, synthetic_series, _stages(translate=True))
    published = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    published.unlink()
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True))
    assert summary.stages["publish"].done == 1 and published.exists()


def test_foreign_ptbr_file_skips_unless_forced(data_dir: Path, synthetic_series: Path) -> None:
    foreign = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    foreign.write_text("legenda de outra pessoa", encoding="utf-8")
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True))
    assert summary.stages["select_track"].skipped == 1
    assert foreign.read_text(encoding="utf-8") == "legenda de outra pessoa"
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True), force=True)
    assert summary.stages["publish"].done == 1
    assert "; TranslaterAny" in foreign.read_text(encoding="utf-8")


def test_write_resilient_to_spurious_brackets(data_dir: Path, synthetic_series: Path) -> None:
    from translaterany.pipeline.registry import register_stage
    from translaterany.pipeline.stage import StageContext, StageScope
    from translaterany.subtitles.texts import UnitTexts

    @register_stage
    class SpuriousTranslateStage(Stage):
        name = "t_spurious"
        version = "1"
        scope = StageScope.EPISODE
        translates = True
        produces_texts = True

        def run(self, ctx: StageContext) -> None:
            texts = {"u1": "Texto com ⟦Spurious⟧ colchetes", "u2": "Texto sem marcadores", "u3": "Placa normal"}
            ctx.output.json(UnitTexts(texts=texts))

    stages: list[Stage] = [
        SelectTrackStage(),
        ExtractStage(),
        NormalizeStage(),
        ClassifyStage(),
        SpuriousTranslateStage(),
        WriteStage(WriteOptions(text_source="t_spurious")),
        PublishStage(),
    ]
    summary, store, s, eps = run_stages(data_dir, synthetic_series, stages)
    assert not summary.failed
    published = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    content = published.read_text(encoding="utf-8")
    assert "Texto com Spurious colchetes" in content
    assert "⟦" not in content and "⟧" not in content

