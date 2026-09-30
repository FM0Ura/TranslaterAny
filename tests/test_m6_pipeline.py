"""Encaixe do M6 no pipeline e ponta a ponta com FakeLLM."""

import re
from pathlib import Path

from mkvtools import Sub, make_mkv, needs_mkvtoolnix

from translaterany.config.loader import load_config
from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.report import build_report
from translaterany.pipeline.runner import Runner
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.subtitles.translator import TranslationBatch, TranslationItem


def test_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert i("translate_songs") < i("review_meaning") < i("colloquial") < i("redistribute_sentences")


def test_redistribute_reads_last_dialogue_stage(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert stages["redistribute_sentences"].dialogue_input == "colloquial"
    cfg.write_text("[stages.colloquial]\nenabled = false\n[stages.review_meaning]\nenabled = false\n", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert stages["redistribute_sentences"].dialogue_input == "translate_dialogue"
    assert "review_meaning" not in stages


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
                pt = {"You've": "Você andou escondendo tudo, seu merda.", "However": "No entanto, eu perdi."}
                text = next(v for k, v in pt.items() if m.group(2).startswith(k))
                items.append(TranslationItem(id=m.group(1), text=text))
        return TranslationBatch(items=items)
    if req.output_type is EditsResponse and req.tag == "review_meaning" and "merda" in req.prompt:
        uid = re.search(r'"id": "(u\d+)", "en": "You', req.prompt).group(1)
        return EditsResponse(edits=[LineEdit(id=uid, new="Você andou escondendo tudo dos vizinhos.")])
    if req.output_type is EditsResponse and req.tag == "colloquial":
        uid = re.search(r'"id": "(u\d+)", "en": "However', req.prompt).group(1)
        return EditsResponse(edits=[LineEdit(id=uid, new="Mas eu perdi.")])
    try:
        return req.output_type()
    except Exception:
        return req.output_type.model_construct()


@needs_mkvtoolnix
def test_m6_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Show (2020)"
    make_mkv(root / "Season 1" / "Show - S01E01.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)
    stages = [MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
              for n in DEFAULT_PIPELINE if n != "remux"]  # fmt: skip
    for index, stage in enumerate(stages):  # como o loader faz: redistribute passa a ler a colloquial
        stage.bind_pipeline(stages[:index], None)
    summary = Runner(stages, store, FakeLLM(script)).run(series, episodes)
    assert not summary.failed
    final = (store.artifact_dir(series.key, episodes[0].key) / "redistribute_sentences.json").read_text()
    assert "merda" not in final and "dos vizinhos" in final and "Mas eu perdi." in final
    manifest = store.load_manifest(series, episodes[0])
    assert manifest.stages["review_meaning"].counters["edits_applied"] == 1
    assert manifest.stages["colloquial"].counters["edits_applied"] == 1
    report = build_report(store, series.key, series.name, [s.name for s in stages])
    assert {"review_meaning", "colloquial"} <= set(report.snapshots)
