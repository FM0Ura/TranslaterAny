"""Etapa translate_signs: traduz placas e elementos gráficos visuais."""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.llm.client import LLMClient
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.signs import translate_signs

logger = logging.getLogger(__name__)


class TranslateSignsOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = "translate"
    fallback_model: str | None = "translategemma"
    max_tokens_per_batch: int = 800


@register_stage
class TranslateSignsStage(Stage):
    name: ClassVar[str] = "translate_signs"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify", "translation_memory")
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = TranslateSignsOptions

    def __init__(
        self,
        client: LLMClient | BaseModel | None = None,
        options: BaseModel | None = None,
        inputs: tuple[str, ...] | None = None,
    ) -> None:
        if isinstance(client, BaseModel) and options is None:
            options = client
            client = None
        if options is None:
            options = TranslateSignsOptions()
        elif not isinstance(options, TranslateSignsOptions):
            options = TranslateSignsOptions.model_validate(options)
        super().__init__(options)
        self.options: TranslateSignsOptions = options
        self.client = client
        if inputs is not None:
            self.inputs = inputs

    def run(self, ctx: StageContext) -> None:
        client = self.client or ctx.llm
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classification = ctx.inputs.json("classify", Classification)

        tm_resolved: dict[str, str] = {}
        try:
            tm_artifact = ctx.inputs.json("translation_memory", TranslationMemoryArtifact)
            tm_resolved = tm_artifact.matched_units
        except Exception:
            pass

        result = translate_signs(
            doc=doc,
            classes=classification,
            tm_resolved=tm_resolved,
            client=client,
            model=self.options.model,
            fallback_model=self.options.fallback_model,
            max_tokens_per_batch=self.options.max_tokens_per_batch,
        )
        ctx.output.json(result)
