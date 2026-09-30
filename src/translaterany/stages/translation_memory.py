"""Etapa translation_memory: consulta e aplica correspondências exatas da TM da série."""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from translaterany.config.loader import default_data_dir
from translaterany.memory.tm import TranslationMemoryStore, normalize_tm_key
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.normalize import NormalizedDoc

logger = logging.getLogger(__name__)


class TranslationMemoryOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    min_dialogue_chars: int = 15


class TranslationMemoryArtifact(BaseModel):
    matched_units: dict[str, str] = Field(default_factory=dict)
    matched_keys: list[str] = Field(default_factory=list)


@register_stage
class TranslationMemoryStage(Stage):
    name: ClassVar[str] = "translation_memory"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify")
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = TranslationMemoryOptions

    def run(self, ctx: StageContext) -> None:
        if not self.options.enabled:
            ctx.output.json(TranslationMemoryArtifact())
            return

        store = getattr(ctx, "store", None)
        if store is None:
            store = getattr(getattr(ctx, "inputs", None), "_store", None)
        if store is None:
            store = ArtifactStore(default_data_dir())

        series = getattr(ctx, "series", None)
        if series is None:
            ctx.output.json(TranslationMemoryArtifact())
            return

        tm_path = store.series_dir(series.key) / "memory" / "translation_memory.yaml"
        tm_store = TranslationMemoryStore(tm_path)

        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classification = ctx.inputs.json("classify", Classification)

        matched_units: dict[str, str] = {}
        matched_keys: list[str] = []
        candidates = 0

        for unit in doc.units:
            u_class = classification.units.get(unit.id)
            if not u_class:
                continue
            cat = u_class.type
            if cat not in ("dialogue", "sign", "song"):
                continue
            candidates += 1

            match = tm_store.lookup(unit.text, cat, min_dialogue_chars=self.options.min_dialogue_chars)
            if match is not None:
                matched_units[unit.id] = match
                matched_keys.append(normalize_tm_key(unit.text))

        count(ctx, "tm_candidates", candidates)
        count(ctx, "tm_hits", len(matched_units))
        ctx.output.json(TranslationMemoryArtifact(matched_units=matched_units, matched_keys=matched_keys))
