"""Etapa translate_songs: traduz músicas e canções."""

from __future__ import annotations

import logging
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from translaterany.languages.registry import LanguageRegistry
from translaterany.llm.client import LLMClient
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.songs import render_songs_system_instructions, translate_songs

logger = logging.getLogger(__name__)


class TranslateSongsOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = "translate"
    fallback_model: str | None = "translategemma"
    max_tokens_per_batch: int = 800
    translate: bool = False  # músicas ficam no original; ligue para traduzi-las
    # linhas de tradução de letra ('op trans') e a glosa inglesa de letras 'romaji\Ninglês' são sempre tratadas;
    # o romaji/karaokê nunca é tocado. 'drop' remove a glosa, 'keep' a deixa em inglês.
    bilingual_gloss: Literal["translate", "drop", "keep"] = "translate"
    max_lines_per_batch: int | None = 1  # uma fala por chamada: evita desalinhamento de IDs


@register_stage
class TranslateSongsStage(Stage):
    name: ClassVar[str] = "translate_songs"
    version: ClassVar[str] = "3"  # 3: traduz linhas de tradução de letra e glosa bilíngue; 2: puladas por padrão
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    produces_texts: ClassVar[bool] = True
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify", "translation_memory")
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = TranslateSongsOptions

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
            options = TranslateSongsOptions()
        elif not isinstance(options, TranslateSongsOptions):
            options = TranslateSongsOptions.model_validate(options)
        super().__init__(options)
        self.options: TranslateSongsOptions = options
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

        result = translate_songs(
            doc=doc,
            classes=classification,
            tm_resolved=tm_resolved,
            client=client,
            model=self.options.model,
            fallback_model=self.options.fallback_model,
            max_tokens_per_batch=self.options.max_tokens_per_batch,
            max_lines_per_batch=self.options.max_lines_per_batch,
            translate_all=self.options.translate,  # sem isto só as linhas de tradução/glosa são tratadas
            bilingual_gloss=self.options.bilingual_gloss,
            metrics=ctx.metrics if isinstance(getattr(ctx, "metrics", None), StageMetrics) else None,
            system_instructions=render_songs_system_instructions(
                getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en"),
                getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR"),
            ),
        )
        ctx.output.json(result)
