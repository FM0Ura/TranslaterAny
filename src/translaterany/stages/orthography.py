"""Etapa orthography: correção ortográfica via LanguageTool local com degradação graciosa (M7)."""

import logging
from collections.abc import Mapping, Sequence, Set
from typing import Any, ClassVar

from pydantic import BaseModel

from translaterany.checks import CheckEnv
from translaterany.checks.snapshots import LineSource, build_sources
from translaterany.config.model import AppConfig, ChecksConfig, OrthographyOptions
from translaterany.memory.matching import load_memory_for_text
from translaterany.orthography.client import LanguageToolClient
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.pipeline.registry import register_stage
from translaterany.refine.edits import LineEdit, apply_edits
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

_OPTIONAL = ("merge_sentences", "consolidate_memory")

HONORIFICS: frozenset[str] = frozenset({
    "kun",
    "chan",
    "san",
    "sama",
    "senpai",
    "sempai",
    "sensei",
    "dono",
    "kouhai",
    "shishou",
    "tan",
    "hakase",
    "niisan",
    "neesan",
    "onii-san",
    "onee-san",
    "onii-chan",
    "onee-chan",
})


@register_stage

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
        self.inputs = ("normalize", "classify", *_OPTIONAL, self.dialogue_input)
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
        base = [n for n in ("normalize", "classify") if n in names]
        self.inputs = (*base, *optional, self.dialogue_input)

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        opts: OrthographyOptions = self.options  # type: ignore[assignment]
        return {"input": self.dialogue_input, "url": opts.url, "language": opts.language}

    def process_texts(
        self,
        texts: Mapping[str, str],
        sources: Mapping[str, LineSource] | None = None,
        exemptions: Set[str] | None = None,
        limits: ChecksConfig | None = None,
        env: CheckEnv | None = None,
    ) -> tuple[dict[str, str], bool, int]:
        """Corrige os textos linha a linha usando LanguageToolClient com validação de integridade."""
        clean_exemptions = {e.lower() for e in (exemptions or set()) if e}
        edits: list[LineEdit] = []

        for uid, text in texts.items():
            corrected, num_corr = self.client.correct_text(text, exemptions=clean_exemptions)
            if self.client.is_offline:
                logger.warning("LanguageTool offline detectado durante o processamento da linha %s.", uid)
                return dict(texts), True, 0
            if num_corr > 0 and corrected != text:
                edits.append(LineEdit(id=uid, new=corrected, reason="LanguageTool"))

        if not edits:
            return dict(texts), False, 0

        if sources:
            check_env = env or CheckEnv(
                glossary=[],
                names=[],
                limits=limits or ChecksConfig(),
            )
            outcome = apply_edits(
                texts=texts,
                edits=edits,
                targets=set(texts.keys()),
                sources=sources,
                env=check_env,
            )
            return outcome.texts, False, len(outcome.applied)

        # Fallback determinístico quando sources não está disponível: valida marcadores e tags
        result = dict(texts)
        applied = 0
        for edit in edits:
            current = texts[edit.id]
            if "{" in edit.new or "}" in edit.new or marker_ids(edit.new) != marker_ids(current):
                continue
            result[edit.id] = edit.new
            applied += 1
        return result, False, applied

    def run(self, ctx: StageContext) -> None:
        dialogue = ctx.inputs.json(self.dialogue_input, UnitTexts)
        texts = dict(dialogue.texts)
        if not texts:
            ctx.output.json(UnitTexts(texts={}, used_terms=dialogue.used_terms))
            return

        doc = ctx.inputs.json("normalize", NormalizedDoc) if "normalize" in self.inputs else None
        classes = ctx.inputs.json("classify", Classification) if "classify" in self.inputs else None
        merged = ctx.inputs.json("merge_sentences", MergedUnitsDoc) if "merge_sentences" in self.inputs else None
        sources = build_sources(doc, classes, merged) if doc and classes else {}

        # Carrega glossário e nomes para isenção pesquisando no texto fonte em EN e no texto em PT-BR
        src_block = "\n".join(sources[i].source for i in texts if i in sources)
        pt_block = "\n".join(texts.values())
        search_block = f"{src_block}\n{pt_block}" if src_block else pt_block

        glossary, characters = load_memory_for_text(
            getattr(ctx, "store", None),
            ctx.series.key,
            search_block,
        )
        exemptions: set[str] = set(HONORIFICS)
        for term in glossary:
            for val in (term.term, term.translation, *term.aliases):
                if val:
                    exemptions.add(val)
                    for word in val.split():
                        cleaned = word.strip("-,.?!:; ")
                        if cleaned:
                            exemptions.add(cleaned)
        for char in characters:
            for val in (char.name, *char.aliases):
                if val:
                    exemptions.add(val)
                    for word in val.split():
                        cleaned = word.strip("-,.?!:; ")
                        if cleaned:
                            exemptions.add(cleaned)

        app_obj = getattr(ctx, "app", None)
        checks_cfg = getattr(app_obj, "checks", None)
        limits = checks_cfg if isinstance(checks_cfg, ChecksConfig) else ChecksConfig()
        env = CheckEnv(
            glossary=glossary,
            names=[[c.name, *c.aliases] for c in characters],
            limits=limits,
        )

        outcome_texts, offline, applied = self.process_texts(
            texts,
            sources=sources,
            exemptions=exemptions,
            env=env,
        )

        count(ctx, "lines_read", len(texts))
        if offline:
            count(ctx, "offline")
            logger.warning("orthography: LanguageTool indisponível; mantendo textos anteriores sem alterações.")
        else:
            count(ctx, "corrections_applied", applied)

        ctx.output.json(UnitTexts(texts=outcome_texts, used_terms=dialogue.used_terms))
