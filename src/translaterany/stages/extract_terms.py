"""Etapa extract_terms: extração de termos e entidades de cada episódio com IA."""

import logging
from typing import ClassVar

from pydantic import BaseModel, Field

from translaterany.llm.client import LLMClient, LLMRequest
from translaterany.memory.artifacts import ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import EntrySource, GlossaryCategory, GlossaryEntry
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


class ExtractTermsResponse(BaseModel):
    terms: list[ExtractedTermItem] = Field(default_factory=list)
    character_mentions: list[str] = Field(default_factory=list)


class ExtractTermsOptions(BaseModel):
    model: str = "review"
    fallback_model: str | None = None
    max_sample_lines: int | None = 500


@register_stage
class ExtractTermsStage(Stage):
    """Etapa de episódio que extrai termos candidatos e menções de personagens."""

    name: ClassVar[str] = "extract_terms"
    version: ClassVar[str] = "1"
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

        if self.options.max_sample_lines is not None:
            sampled_units = units[: self.options.max_sample_lines]
        else:
            sampled_units = units

        sample_lines = "\n".join(f"- {u.text}" for u in sampled_units)
        prompt = (
            f"{chr(10).join(context_parts)}\n\n"
            f"Episode dialogue lines:\n{sample_lines}\n\n"
            "Identify key terminology, abilities, locations, organizations, and mentioned characters."
        )

        instructions = (
            "You are an expert anime terminology analyst. Analyze dialogue lines and metadata "
            "to extract recurring non-trivial proper nouns, abilities, locations, organizations, and jargon. "
            "For each term, provide a natural PT-BR translation and an appropriate category "
            "('name', 'place', 'technique', 'object', 'org', or 'general'). "
            "Also list character names mentioned in the dialogue."
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
        )
        ctx.output.json(artifact)


__all__ = ["ExtractTermsOptions", "ExtractTermsResponse", "ExtractTermsStage"]
