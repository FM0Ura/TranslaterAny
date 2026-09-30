"""Etapa merge_sentences: agrupa falas consecutivas em frases completas."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc, merge_dialogue_units
from translaterany.subtitles.normalize import NormalizedDoc


class MergeSentencesOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_gap_ms: int = 1500


@register_stage
class MergeSentencesStage(Stage):
    name: ClassVar[str] = "merge_sentences"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify", "translation_memory")
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = MergeSentencesOptions

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classification = ctx.inputs.json("classify", Classification)

        tm_resolved_ids: set[str] = set()
        try:
            tm_art = ctx.inputs.json("translation_memory", TranslationMemoryArtifact)
            tm_resolved_ids = set(tm_art.matched_units.keys())
        except Exception:
            pass

        merged_doc = merge_dialogue_units(
            doc=doc,
            classes=classification.units,
            tm_resolved_ids=tm_resolved_ids,
            max_gap_ms=self.options.max_gap_ms,
        )
        groups = [c for c in merged_doc.units if len(c.unit_ids) > 1]
        count(ctx, "merged_groups", len(groups))
        count(ctx, "merged_units", sum(len(c.unit_ids) for c in groups))
        ctx.output.json(merged_doc)
