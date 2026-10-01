"""Etapa orthography: correção ortográfica via LanguageTool local com degradação graciosa (M7)."""

import logging
from collections.abc import Mapping, Sequence, Set
from typing import Any, ClassVar

from pydantic import BaseModel

from translaterany.config.model import AppConfig, OrthographyOptions
from translaterany.memory.matching import load_memory_for_text
from translaterany.orthography.client import LanguageToolClient
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

_OPTIONAL = ("consolidate_memory",)


class OrthographyStage(Stage):
    """Revisão ortográfica determinística com LanguageTool sem IA."""

    name: ClassVar[str] = "orthography"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    produces_texts: ClassVar[bool] = True
    produces_dialogue: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = OrthographyOptions
    default_dialogue_input: ClassVar[str] = "adapt"

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.dialogue_input = self.default_dialogue_input
        self.inputs = (*_OPTIONAL, self.dialogue_input)
        self.client = self.make_client()

    def make_client(self, transport: Any = None) -> LanguageToolClient:
        opts: OrthographyOptions = self.options  # type: ignore[assignment]
        return LanguageToolClient(
            url=opts.url,
            timeout_s=opts.timeout_s,
            language=opts.language,
            transport=transport,
        )

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        names = [s.name for s in previous]
        dialogue = [s.name for s in previous if s.produces_dialogue]
        if dialogue:
            self.dialogue_input = dialogue[-1]
        optional = tuple(n for n in _OPTIONAL if n in names)
        self.inputs = (*optional, self.dialogue_input)

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        opts: OrthographyOptions = self.options  # type: ignore[assignment]
        return {"input": self.dialogue_input, "url": opts.url, "language": opts.language}

    def process_texts(
        self,
        texts: Mapping[str, str],
        exemptions: Set[str] | None = None,
    ) -> tuple[dict[str, str], bool, int]:
        """Corrige os textos linha a linha usando LanguageToolClient."""
        result = dict(texts)
        total_applied = 0
        clean_exemptions = {e.lower() for e in (exemptions or set())}

        for uid, text in texts.items():
            corrected, applied = self.client.correct_text(text, exemptions=clean_exemptions)
            if self.client.is_offline:
                logger.warning("LanguageTool offline detectado durante o processamento da linha %s.", uid)
                return dict(texts), True, 0
            if applied > 0:
                result[uid] = corrected
                total_applied += applied

        return result, False, total_applied

    def run(self, ctx: StageContext) -> None:
        dialogue = ctx.inputs.json(self.dialogue_input, UnitTexts)
        texts = dict(dialogue.texts)
        if not texts:
            ctx.output.json(UnitTexts(texts={}, used_terms=dialogue.used_terms))
            return

        # Carrega glossário e nomes para isenção
        glossary, characters = load_memory_for_text(
            getattr(ctx, "store", None),
            ctx.series.key,
            "\n".join(texts.values()),
        )
        exemptions: set[str] = set()
        for term in glossary:
            exemptions.add(term.source)
            exemptions.add(term.target)
            exemptions.update(term.aliases)
        for char in characters:
            exemptions.add(char.name)
            exemptions.update(char.aliases)

        outcome_texts, offline, applied = self.process_texts(texts, exemptions=exemptions)

        count(ctx, "lines_read", len(texts))
        if offline:
            count(ctx, "offline")
            logger.warning("orthography: LanguageTool indisponível; mantendo textos anteriores sem alterações.")
        else:
            count(ctx, "corrections_applied", applied)

        ctx.output.json(UnitTexts(texts=outcome_texts, used_terms=dialogue.used_terms))
