"""Etapa extract_terms: extração de termos e entidades de cada episódio com IA."""

import logging
from typing import ClassVar

from pydantic import BaseModel, Field

from translaterany.llm.client import LLMClient, LLMRequest
from translaterany.memory.artifacts import CharacterStyle, ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import EntrySource, GlossaryCategory, GlossaryEntry
from translaterany.memory.styles import find_character
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.normalize import NormalizedDoc

logger = logging.getLogger(__name__)

_CATEGORY_MAP: dict[str, GlossaryCategory] = {
    "name": GlossaryCategory.NAME,
    "person": GlossaryCategory.NAME,
    "character": GlossaryCategory.NAME,
    "place": GlossaryCategory.PLACE,
    "location": GlossaryCategory.PLACE,
    "technique": GlossaryCategory.TECHNIQUE,
    "ability": GlossaryCategory.TECHNIQUE,
    "skill": GlossaryCategory.TECHNIQUE,
    "power": GlossaryCategory.TECHNIQUE,
    "object": GlossaryCategory.OBJECT,
    "item": GlossaryCategory.OBJECT,
    "org": GlossaryCategory.ORGANIZATION,
    "organization": GlossaryCategory.ORGANIZATION,
    "general": GlossaryCategory.GENERAL,
}


class ExtractedTermItem(BaseModel):
    term: str
    translation: str = ""
    category: str = "general"
    keep_original: bool = False
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None


class ExtractedCharacterStyle(BaseModel):
    name: str
    speech_style: str = ""


class ExtractTermsResponse(BaseModel):
    terms: list[ExtractedTermItem] = Field(default_factory=list)
    character_mentions: list[str] = Field(default_factory=list)
    character_styles: list[ExtractedCharacterStyle] = Field(default_factory=list)


class ExtractTermsOptions(BaseModel):
    model: str = "review"
    fallback_model: str | None = None
    max_sample_lines: int | None = 500


def sample_evenly[T](items: list[T], limit: int | None) -> list[T]:
    """Até `limit` itens espaçados uniformemente (mantém ordem, primeiro e último) para cobrir o episódio inteiro."""
    if limit is None or limit >= len(items):
        return items
    if limit <= 1:
        return items[:limit]
    last = len(items) - 1
    return [items[round(i * last / (limit - 1))] for i in range(limit)]


def _clean_styles(items: list[ExtractedCharacterStyle], meta: MetadataArtifact | None) -> list[CharacterStyle]:
    """Descarta estilos vazios/duplicados e troca o nome pelo do personagem dos metadados quando casa."""
    known = meta.characters if meta else []
    cleaned: list[CharacterStyle] = []
    seen: set[str] = set()
    for item in items:
        name = " ".join(item.name.split())
        style = " ".join(item.speech_style.split())
        if not name or not style:
            continue
        idx = find_character(known, name)
        if idx is not None:
            name = known[idx].name
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        cleaned.append(CharacterStyle(name=name, speech_style=style))
    return cleaned


@register_stage
class ExtractTermsStage(Stage):
    """Etapa de episódio que extrai termos candidatos e menções de personagens."""

    name: ClassVar[str] = "extract_terms"
    version: ClassVar[str] = "2"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    inputs: ClassVar[tuple[str, ...]] = ("metadata", "normalize")
    translates: ClassVar[bool] = False
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = ExtractTermsOptions

    def __init__(
        self,
        client: LLMClient | BaseModel | None = None,
        options: BaseModel | None = None,
    ) -> None:
        if isinstance(client, BaseModel) and options is None:
            options = client
            client = None
        if options is None:
            options = ExtractTermsOptions()
        elif not isinstance(options, ExtractTermsOptions):
            options = ExtractTermsOptions.model_validate(options)
        super().__init__(options)
        self.options: ExtractTermsOptions = options
        self.client = client

    def run(self, ctx: StageContext) -> None:
        client = self.client or getattr(ctx, "llm", None)
        ep_key = ctx.episode.key if ctx.episode else ""

        try:
            doc = ctx.inputs.json("normalize", NormalizedDoc)
        except Exception:
            doc = None

        try:
            meta = ctx.inputs.json("metadata", MetadataArtifact)
        except Exception:
            meta = None

        units = [u for u in doc.units if u.text.strip()] if doc and doc.units else []
        if not units or not client:
            ctx.output.json(
                ExtractTermsArtifact(
                    episode_key=ep_key,
                    terms=[],
                    character_mentions=[],
                )
            )
            return

        context_parts: list[str] = []
        if meta:
            if meta.title:
                context_parts.append(f"Anime Title: {meta.title}")
            if meta.characters:
                names = [c.name for c in meta.characters[:20]]
                context_parts.append(f"Known characters from metadata: {', '.join(names)}")

        sampled_units = sample_evenly(units, self.options.max_sample_lines)

        sample_lines = "\n".join(f"- {u.text}" for u in sampled_units)
        prompt = (
            f"{chr(10).join(context_parts)}\n\n"
            f"Episode dialogue lines:\n{sample_lines}\n\n"
            "Identify key terminology, abilities, locations, organizations, mentioned characters, "
            "and the speech style of the characters who speak."
        )

        instructions = (
            "You are an expert anime terminology analyst. Analyze dialogue lines and metadata "
            "to extract recurring non-trivial proper nouns, abilities, locations, organizations, and jargon. "
            "For each term, provide a natural PT-BR translation and an appropriate category "
            "('name', 'place', 'technique', 'object', 'org', or 'general'). "
            "Also list character names mentioned in the dialogue. "
            "Finally, fill character_styles with one {name, speech_style} item per character whose way of "
            "speaking you can actually characterize from the lines: speech_style is a short PT-BR description "
            "of register, verbal tics and politeness (e.g. 'formal e educado, usa tom sarcástico'). "
            "Use the exact names from the known characters list when the character is in it, "
            "and omit characters you cannot characterize."
        )

        req = LLMRequest(
            model=self.options.model,
            instructions=instructions,
            prompt=prompt,
            output_type=ExtractTermsResponse,
            tag="extract_terms",
        )

        try:
            resp = client.generate(req)
            llm_output = resp.output
        except Exception as exc:
            if self.options.fallback_model and self.options.fallback_model != self.options.model:
                logger.warning(
                    "Falha ao chamar modelo primário '%s' (%s). Tentando fallback '%s'.",
                    self.options.model,
                    exc,
                    self.options.fallback_model,
                )
                fallback_req = LLMRequest(
                    model=self.options.fallback_model,
                    instructions=instructions,
                    prompt=prompt,
                    output_type=ExtractTermsResponse,
                    tag="extract_terms",
                )
                resp = client.generate(fallback_req)
                llm_output = resp.output
            else:
                raise

        entries: list[GlossaryEntry] = []
        seen_terms: set[str] = set()
        for item in llm_output.terms:
            clean_term = item.term.strip()
            if not clean_term:
                continue
            key = clean_term.lower()
            if key in seen_terms:
                continue
            seen_terms.add(key)

            cat = _CATEGORY_MAP.get(str(item.category).strip().lower(), GlossaryCategory.GENERAL)
            entries.append(
                GlossaryEntry(
                    term=clean_term,
                    translation=item.translation.strip(),
                    category=cat,
                    keep_original=item.keep_original,
                    aliases=[a.strip() for a in item.aliases if a.strip()],
                    notes=item.notes,
                    source=EntrySource.EXTRACTED,
                )
            )

        unique_mentions: list[str] = []
        seen_mentions: set[str] = set()
        for m in llm_output.character_mentions:
            m_clean = m.strip()
            if not m_clean:
                continue
            if m_clean.lower() not in seen_mentions:
                seen_mentions.add(m_clean.lower())
                unique_mentions.append(m_clean)

        artifact = ExtractTermsArtifact(
            episode_key=ep_key,
            terms=entries,
            character_mentions=unique_mentions,
            character_styles=_clean_styles(llm_output.character_styles, meta),
        )
        ctx.output.json(artifact)


__all__ = ["ExtractTermsOptions", "ExtractTermsResponse", "ExtractTermsStage"]
