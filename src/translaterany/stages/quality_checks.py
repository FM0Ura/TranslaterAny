"""Etapa quality_checks: mede cada instantâneo de texto e grava metrics.json (camada 2). Nunca corrige nada."""

import logging
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.checks import CheckEnv, Finding, run_line_checks
from translaterany.checks.fonts import check_font_glyphs, event_fonts, load_font_faces, style_fonts
from translaterany.checks.metrics import EpisodeMetrics, FinalMetrics, SnapshotMetrics
from translaterany.checks.snapshots import (
    LineSource,
    advance_state,
    build_sources,
    composite_members,
    compute_delta,
    finding_keys,
    flagged,
    lines_for,
    reading_speed_stats,
    summarize,
)
from translaterany.checks.text import plain
from translaterany.config.model import AppConfig, ChecksConfig
from translaterany.media.mkv import extract_attachments, font_attachments, probe
from translaterany.memory.matching import load_memory_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOTS: tuple[str, ...] = (
    "translate_dialogue",
    "translate_signs",
    "translate_songs",
    "redistribute_sentences",
)
_OPTIONAL = ("extract", "merge_sentences", "consolidate_memory")
_EXCERPT = 60


class QualityChecksOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fonts: bool = True


def assemble_metrics(
    snapshots: Sequence[tuple[str, Mapping[str, str]]],
    sources: Mapping[str, LineSource],
    composites: Mapping[str, list[str]],
    env: CheckEnv,
    episode_checks: list[Finding],
) -> tuple[EpisodeMetrics, dict[str, str]]:
    """Parte pura da etapa: instantâneos (nome, textos) em ordem -> (métricas, estado final)."""
    state: dict[str, str] = {}
    state_findings: list[Finding] = []
    result: list[SnapshotMetrics] = []
    for name, texts in snapshots:
        delivered, unknown = lines_for(texts, sources)
        if unknown:
            logger.warning("quality_checks: %s tem chaves desconhecidas: %s", name, ", ".join(unknown[:5]))
        new_state = advance_state(state, texts, composites)
        new_findings = run_line_checks(lines_for(new_state, sources)[0], env)
        result.append(
            SnapshotMetrics(
                stage=name,
                lines=len(delivered),
                checks=summarize(run_line_checks(delivered, env)),
                delta=compute_delta(state, new_state, finding_keys(state_findings), finding_keys(new_findings)),
            )
        )
        state, state_findings = new_state, new_findings

    final_lines, _ = lines_for(state, sources)
    for f in state_findings:
        if f.unit_id in state:
            f.excerpt = plain(state[f.unit_id])[:_EXCERPT]
    by_type: dict[str, int] = {}
    for line in final_lines:
        by_type[line.line_type] = by_type.get(line.line_type, 0) + 1
    final = FinalMetrics(
        lines=len(final_lines),
        by_type=by_type,
        checks=summarize(state_findings),
        flagged_lines=flagged(state_findings),
        lines_by_check={
            check: flagged(f for f in state_findings if f.check == check) for check in {f.check for f in state_findings}
        },
        reading_speed=reading_speed_stats(final_lines, env.limits),
        findings=state_findings,
    )
    return EpisodeMetrics(snapshots=result, final=final, episode_checks=episode_checks), state


@register_stage
class QualityChecksStage(Stage):
    name: ClassVar[str] = "quality_checks"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    reads_source: ClassVar[bool] = True  # extrai as fontes anexadas
    Options: ClassVar[type[BaseModel]] = QualityChecksOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.snapshots: list[str] = list(DEFAULT_SNAPSHOTS)
        self.limits = ChecksConfig()
        self.inputs = ("normalize", "classify", *_OPTIONAL, *self.snapshots)

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        names = [s.name for s in previous]
        self.snapshots = [s.name for s in previous if s.produces_texts]
        self.limits = app.checks if app is not None else ChecksConfig()
        self.inputs = ("normalize", "classify", *(n for n in _OPTIONAL if n in names), *self.snapshots)

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        return {"limits": self.limits.model_dump(mode="json"), "snapshots": self.snapshots}

    def env_for(self, glossary: list[GlossaryEntry], characters: list[CharacterEntry]) -> CheckEnv:
        return CheckEnv(
            glossary=glossary,
            names=[[c.name, *c.aliases] for c in characters],
            limits=self.limits,
        )

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classes = ctx.inputs.json("classify", Classification)
        merged = ctx.inputs.json("merge_sentences", MergedUnitsDoc) if "merge_sentences" in self.inputs else None
        sources = build_sources(doc, classes, merged)
        glossary, characters = self._memory(ctx, "\n".join(u.text for u in doc.units))
        snapshots = [(name, ctx.inputs.json(name, UnitTexts).texts) for name in self.snapshots]
        env = self.env_for(glossary, characters)
        metrics, final_state = assemble_metrics(snapshots, sources, composite_members(merged), env, [])
        if self.options.fonts and "extract" in self.inputs:
            metrics.episode_checks = self._font_checks(ctx, doc, final_state)
        ctx.output.json(metrics)

    def _memory(self, ctx: StageContext, text: str) -> tuple[list[GlossaryEntry], list[CharacterEntry]]:
        return load_memory_for_text(ctx.store, ctx.series.key, text)

    def _font_checks(self, ctx: StageContext, doc: NormalizedDoc, state: Mapping[str, str]) -> list[Finding]:
        assert ctx.episode is not None
        try:
            styles = style_fonts(ctx.inputs.path("extract").read_bytes())
            chars_by_font: dict[str, set[str]] = {}
            for event in doc.events:
                if event.unit is None or event.unit not in state:
                    continue
                for font in event_fonts(event, styles):
                    chars_by_font.setdefault(font, set()).update(plain(state[event.unit]))
            if not chars_by_font:
                return []
            with tempfile.TemporaryDirectory(prefix="translaterany-fonts-") as tmp:
                files = extract_attachments(ctx.episode.source, font_attachments(probe(ctx.episode.source)), Path(tmp))
                faces, problems = load_font_faces(files)
                return problems + check_font_glyphs(chars_by_font, faces)
        except Exception as exc:  # fontes nunca derrubam o episódio
            message = f"fontes não verificadas: {type(exc).__name__}: {exc}"
            return [Finding(check="font_glyphs", severity="info", message=message)]
