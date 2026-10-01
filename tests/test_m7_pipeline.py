"""Teste ponta a ponta do pipeline com as etapas do M7."""

from pathlib import Path
import re

from mkvtools import Sub, make_mkv, needs_mkvtoolnix
from translaterany.config.loader import load_config
from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import TranslationBatch, TranslationItem


def test_m7_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert (
        i("colloquial")
        < i("treatment_consistency")
        < i("adapt")
        < i("orthography")
        < i("final_readthrough")
        < i("redistribute_sentences")
    )


def test_redistribute_reads_final_readthrough(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert stages["redistribute_sentences"].dialogue_input == "final_readthrough"


ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:00.00,0:01:03.00,Default,,0,0,0,,You've been hiding it from all the neighbors.
Dialogue: 0,0:01:04.00,0:01:07.00,Default,,0,0,0,,However, I lost it.
"""


def script(req):
    if req.output_type is TranslationBatch:
        items = []
        for line in req.prompt.splitlines():
            m = re.match(r"^\[(u[^\]]+)\]\s*(.*)$", line.strip())
            if m:
                text = "Você andou escondendo isso dos vizinhos." if "hiding" in m.group(2) else "No entanto, eu perdi."
                items.append(TranslationItem(id=m.group(1), text=text))
        return TranslationBatch(items=items)
    if req.output_type is EditsResponse:
        return EditsResponse(edits=[])
    try:
        return req.output_type()
    except Exception:
        return req.output_type.model_construct()


@needs_mkvtoolnix
def test_m7_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Show (2020)"
    make_mkv(root / "Season 1" / "Show - S01E01.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)

    stages = [
        MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
        for n in DEFAULT_PIPELINE
        if n != "remux"
    ]
    for index, stage in enumerate(stages):
        stage.bind_pipeline(stages[:index], None)

    summary = Runner(stages, store, FakeLLM(script)).run(series, episodes)
    assert not summary.failed

    ep = episodes[0]
    art_dir = store.artifact_dir(series.key, ep.key)
    assert (art_dir / "treatment_consistency.json").exists()
    assert (art_dir / "adapt.json").exists()
    assert (art_dir / "orthography.json").exists()
    assert (art_dir / "final_readthrough.json").exists()

    final_dialogue = UnitTexts.model_validate_json((art_dir / "final_readthrough.json").read_text(encoding="utf-8"))
    assert len(final_dialogue.texts) > 0
