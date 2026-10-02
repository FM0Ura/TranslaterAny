"""Teste ponta a ponta do pipeline com StageGate e QALoopStage (M8)."""

import json
import re
from pathlib import Path

from mkvtools import Sub, make_mkv, needs_mkvtoolnix

from translaterany.config.loader import load_config
from translaterany.library import discover
from translaterany.llm.client import LLMRequest
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.refine.edits import EditsResponse
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.subtitles.translator import TranslationBatch, TranslationItem


def test_m8_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert i("final_readthrough") < i("redistribute_sentences") < i("qa_loop") < i("write") < i("quality_checks")


def test_qa_loop_in_default_config(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert "qa_loop" in stages
    assert stages["quality_checks"].inputs is not None
    assert "qa_loop" in stages["write"].inputs


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


def script(req: LLMRequest):
    if req.output_type is TranslationBatch:
        if req.tag and req.tag.startswith("qa_loop"):
            return TranslationBatch(items=[TranslationItem(id="u1", text="Você andou escondendo isso dos vizinhos.")])
        items = []
        for line in req.prompt.splitlines():
            m = re.match(r"^\[(u[^\]]+)\]\s*(.*)$", line.strip())
            if m:
                uid, text = m.group(1), m.group(2)
                if "hiding" in text:
                    tr = "máx. 10 Você andou escondendo isso dos vizinhos."
                else:
                    tr = "No entanto, eu perdi."
                items.append(TranslationItem(id=uid, text=tr))
        return TranslationBatch(items=items)

    if req.output_type is EditsResponse:
        return EditsResponse(edits=[])

    try:
        return req.output_type()
    except Exception:
        return req.output_type.model_construct()


@needs_mkvtoolnix
def test_m8_end_to_end(tmp_path: Path) -> None:
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

    # 1. Valida que o artefato do qa_report foi gerado com sucesso
    qa_report_path = art_dir / "qa_report.json"
    assert qa_report_path.exists()
    qa_data = json.loads(qa_report_path.read_text(encoding="utf-8"))

    # 2. Valida atribuição de culpa e intervenção no relatório
    assert qa_data["blame_summary"]["translate_dialogue"] >= 1
    assert any(
        interv["unit_id"] == "u1" and interv["blamed_stage"] == "translate_dialogue" and interv["outcome"] == "fixed"
        for interv in qa_data["interventions"]
    )

    # 3. Valida que o arquivo final publicado .pt-BR.ass contém a versão corrigida pelo QA Loop
    published_ass = root / "Season 1" / "Show - S01E01.pt-BR.ass"
    assert published_ass.exists()
    ass_text = published_ass.read_text(encoding="utf-8")
    assert "máx. 10" not in ass_text
    assert "Você andou escondendo isso dos vizinhos." in ass_text
    assert "No entanto, eu perdi." in ass_text
