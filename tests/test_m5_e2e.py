"""Ponta a ponta do M5: pipeline completo com FakeLLM -> metrics.json -> report."""

from pathlib import Path

from mkvtools import Sub, make_mkv, needs_mkvtoolnix

from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.report import build_report
from translaterany.pipeline.runner import Runner
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage

pytestmark = needs_mkvtoolnix

ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:00.00,0:01:03.00,Default,,0,0,0,,Where are we going, friend?
Dialogue: 0,0:01:04.00,0:01:04.50,Default,,0,0,0,,I never said that I would come with you today.
"""


def test_m5_pipeline_metrics_and_report(tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Show (2020)"
    for ep in (1, 2):
        make_mkv(root / "Season 1" / f"Show - S01E0{ep}.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)
    stages = [
        MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
        for n in DEFAULT_PIPELINE
        if n != "remux"
    ]
    llm = FakeLLM(responses={
        "Where are we going, friend?": "Aonde vamos, amigo?",
        "I never said that I would come with you today.": "Eu disse que viria com você hoje.",
    })  # fmt: skip
    summary = Runner(stages, store, llm, prices=lambda alias: (1.0, 2.0)).run(series, episodes)
    assert not summary.failed

    report = build_report(store, series.key, series.name, [s.name for s in stages])
    assert report.episodes == 2 and not report.missing_metrics
    assert report.stages["translate_dialogue"].llm.calls >= 2
    assert report.stages["translate_dialogue"].counters["lines"] >= 2
    assert report.stages["translate_dialogue"].llm.cost_usd > 0  # prices=(1.0, 2.0) USD/Mtok
    assert sum(m.cost_usd for m in report.models.values()) >= report.stages["translate_dialogue"].llm.cost_usd
    assert report.final_checks["negation"].counts.warn == 2  # um por episódio
    assert report.final_checks["reading_speed"].counts.error >= 2  # 46 caracteres em 0,5 s
    assert "redistribute_sentences" in report.snapshots
