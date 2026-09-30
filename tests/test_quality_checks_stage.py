# tests/test_quality_checks_stage.py
"""Etapa quality_checks (M5)."""

from pathlib import Path

from mkvtools import needs_mkvtoolnix

from translaterany.checks.metrics import EpisodeMetrics
from translaterany.config.model import AppConfig, ChecksConfig
from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.units import Series
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.stages.quality_checks import DEFAULT_SNAPSHOTS, QualityChecksStage, assemble_metrics


def test_is_last_in_default_pipeline() -> None:
    assert DEFAULT_PIPELINE[-1] == "quality_checks"


def test_defaults_without_binding() -> None:
    stage = QualityChecksStage()
    assert stage.snapshots == list(DEFAULT_SNAPSHOTS)
    assert set(DEFAULT_SNAPSHOTS) <= set(stage.inputs)
    assert stage.limits == ChecksConfig()


def test_bind_pipeline_discovers_snapshots_and_optional_inputs() -> None:
    previous = [REGISTRY.get(n)() for n in ("select_track", "extract", "normalize", "classify", "translation_memory",
                                             "translate_signs")]  # fmt: skip
    stage = QualityChecksStage()
    stage.bind_pipeline(previous, AppConfig.model_validate({"checks": {"max_cps": 15}}))
    assert stage.snapshots == ["translate_signs"]
    assert stage.inputs == ("normalize", "classify", "extract", "translate_signs")  # sem merge/consolidate
    assert stage.limits.max_cps == 15.0


def test_cache_payload_changes_with_limits() -> None:
    a, b = QualityChecksStage(), QualityChecksStage()
    b.limits = ChecksConfig(max_cps=20)
    series = Series(name="x")
    assert a.cache_payload(series, None) != b.cache_payload(series, None)


ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48
Style: Sign,Arial,40

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:02:00.00,0:02:05.00,Sign,,0,0,0,,Student Council
Dialogue: 0,0:03:00.00,0:03:02.00,Default,,0,0,0,,Wait for me...
Dialogue: 0,0:03:02.20,0:03:04.00,Default,,0,0,0,,...I am coming!
Dialogue: 0,0:04:00.00,0:04:01.00,Default,,0,0,0,,I don't know what you are talking about at all.
"""


@needs_mkvtoolnix
def test_stage_writes_metrics_with_snapshots(tmp_path: Path) -> None:
    from mkvtools import Sub, make_mkv

    root = tmp_path / "lib" / "Show (2020)"
    make_mkv(root / "Season 1" / "Show - S01E01.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)
    stages = []
    for name in DEFAULT_PIPELINE:
        if name == "remux":
            continue
        if name == "metadata":
            stages.append(MetadataStage(anilist_client=None, jikan_client=None))
        else:
            stages.append(REGISTRY.get(name)())
    llm = FakeLLM(responses={
        "Student Council": "Conselho Estudantil",
        "Wait for me... ...I am coming!": "Espere por mim... já estou chegando!",
        "I don't know what you are talking about at all.": "Sei do que você fala, com toda a certeza do mundo.",
    })  # fmt: skip
    summary = Runner(stages, store, llm).run(series, episodes)
    assert not summary.failed, summary
    path = store.artifact_dir(series.key, episodes[0].key) / "quality_checks.json"
    metrics = EpisodeMetrics.model_validate_json(path.read_text(encoding="utf-8"))
    assert [s.stage for s in metrics.snapshots] == list(DEFAULT_SNAPSHOTS)
    assert metrics.final.lines == 4
    assert metrics.final.by_type == {"dialogue": 3, "sign": 1}
    checks = {f.check for f in metrics.final.findings}
    assert "negation" in checks and "reading_speed" in checks  # 50 chars em 1 s
    assert all(f.excerpt is not None for f in metrics.final.findings)
    redistribute = metrics.snapshots[-1]
    assert redistribute.delta.changed >= 2  # composto virou duas unidades
    assert any(f.check == "font_glyphs" for f in metrics.episode_checks)  # fontes falsas do mkvtools: info


def test_empty_snapshots_still_write_valid_metrics() -> None:
    metrics, state = assemble_metrics(
        snapshots=[], sources={}, composites={}, env=QualityChecksStage().env_for([], []), episode_checks=[]
    )
    assert state == {}
    assert metrics.final.lines == 0 and metrics.final.reading_speed.cps_p50 == 0.0
    assert metrics.snapshots == []
