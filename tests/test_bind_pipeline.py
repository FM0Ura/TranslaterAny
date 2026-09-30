# tests/test_bind_pipeline.py
"""Gancho bind_pipeline e flag produces_texts (M5)."""

from collections.abc import Sequence
from pathlib import Path

from fake_stages import SourceStage, Text

import translaterany.stages  # noqa: F401 — registra as etapas reais
from translaterany.config.loader import load_config
from translaterany.config.model import AppConfig
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class SeesPipeline(Stage):
    name = "t_sees"
    version = "1"
    scope = StageScope.EPISODE
    seen: list[str] = []
    max_cps: float = 0.0

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        type(self).seen = [s.name for s in previous]
        type(self).max_cps = app.checks.max_cps if app else 0.0
        self.inputs = tuple(s.name for s in previous if s.name == "t_source")

    def run(self, ctx: StageContext) -> None:
        ctx.output.json(Text(text=ctx.inputs.json("t_source", Text).text))


def test_produces_texts_flags() -> None:
    assert Stage.produces_texts is False
    for name in ("translate_dialogue", "translate_signs", "translate_songs", "redistribute_sentences"):
        assert REGISTRY.get(name).produces_texts is True
    assert REGISTRY.get("normalize").produces_texts is False


def test_loader_binds_with_enabled_previous_stages(tmp_path: Path) -> None:
    if "t_sees" not in REGISTRY:
        REGISTRY.register(SeesPipeline)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[pipeline]\nstages = ["t_source", "t_upper", "t_sees"]\n[stages.t_upper]\nenabled = false\n'
        "[checks]\nmax_cps = 15\n",
        encoding="utf-8",
    )
    resolved = load_config(cfg, tmp_path / "data")
    assert [s.name for s in resolved.stages] == ["t_source", "t_sees"]
    assert SeesPipeline.seen == ["t_source"]  # t_upper desabilitada não aparece
    assert SeesPipeline.max_cps == 15.0
    assert resolved.stages[1].inputs == ("t_source",)  # entradas definidas pelo gancho foram validadas
    assert isinstance(resolved.stages[0], SourceStage)
