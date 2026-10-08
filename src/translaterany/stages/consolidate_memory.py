"""Etapa consolidate_memory: consolidação da memória da série (personagens, glossário e história)."""

import hashlib
import logging
from typing import ClassVar

from translaterany.memory.artifacts import ConsolidatedMemoryArtifact, ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import CharacterEntry, EntrySource, StoryMemory
from translaterany.memory.nicknames import merge_nickname_characters
from translaterany.memory.sanitize import sanitize_glossary
from translaterany.memory.store import MemoryStore
from translaterany.memory.styles import (
    apply_character_styles,
    can_add_alias,
    character_tokens,
    is_valid_character_token,
    resolve_character,
)
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope

logger = logging.getLogger(__name__)


@register_stage
class ConsolidateMemoryStage(Stage):
    """Etapa de série que consolida termos e personagens em arquivos YAML e gera consolidate_memory.json."""

    name: ClassVar[str] = "consolidate_memory"
    version: ClassVar[str] = "3"
    scope: ClassVar[StageScope] = StageScope.SERIES
    inputs: ClassVar[tuple[str, ...]] = ("metadata", "extract_terms")
    translates: ClassVar[bool] = False
    enabled_by_default: ClassVar[bool] = True

    def run(self, ctx: StageContext) -> None:
        store = getattr(ctx, "store", None)
        if store is None:
            store = getattr(getattr(ctx, "inputs", None), "_store", None)
        if store is None:
            from translaterany.config.loader import default_data_dir

            store = ArtifactStore(default_data_dir())

        mem_dir = store.series_dir(ctx.series.key) / "memory"
        mem_store = MemoryStore(mem_dir)

        # 1. Carrega metadados externos
        meta: MetadataArtifact | None = None
        try:
            meta = ctx.inputs.json("metadata", MetadataArtifact)
        except Exception as exc:
            logger.debug("Metadados não disponíveis para consolidar: %s", exc)

        # 2. Carrega extração de termos de todos os episódios
        episodes_extracts: dict[str, ExtractTermsArtifact] = {}
        try:
            episodes_extracts = ctx.inputs.json_all("extract_terms", ExtractTermsArtifact)
        except Exception as exc:
            logger.debug("Artefatos extract_terms não disponíveis: %s", exc)

        # 3. Consolidação de Personagens
        existing_chars = mem_store.load_characters()
        incoming_chars: list[CharacterEntry] = []
        if meta and meta.characters:
            for c in meta.characters:
                src = EntrySource.METADATA if c.source == EntrySource.EXTRACTED else c.source
                incoming_chars.append(c.model_copy(update={"source": src}))

        # Agrupa menções de personagens nos episódios
        all_mentions: list[str] = []
        for ep_art in episodes_extracts.values():
            if ep_art and ep_art.character_mentions:
                all_mentions.extend(ep_art.character_mentions)

        # Combina menções com personagens existentes ou de metadados
        for mention in all_mentions:
            m_clean = mention.strip()
            if not m_clean:
                continue

            matched = False
            m_norm = m_clean.strip(".,!?:;\"'").lower()
            is_valid_mention_token = is_valid_character_token(m_clean)

            # Verifica nos personagens de metadados recebidos
            for c in incoming_chars:
                aliases_lower = [a.lower() for a in c.aliases]
                is_exact_match = m_clean.lower() == c.name.lower() or m_clean.lower() in aliases_lower
                valid_tokens = character_tokens(c.name)
                is_token_match = is_valid_mention_token and m_norm in valid_tokens

                if is_exact_match or is_token_match:
                    matched = True
                    if m_clean.lower() != c.name.lower() and m_clean not in c.aliases:
                        c.aliases.append(m_clean)
                    break

            if not matched:
                # Verifica nos personagens pré-existentes em disco
                for ec in existing_chars:
                    aliases_lower = [a.lower() for a in ec.aliases]
                    is_exact_match = m_clean.lower() == ec.name.lower() or m_clean.lower() in aliases_lower
                    valid_tokens = character_tokens(ec.name)
                    is_token_match = is_valid_mention_token and m_norm in valid_tokens

                    if is_exact_match or is_token_match:
                        matched = True
                        if m_clean.lower() != ec.name.lower() and m_clean not in ec.aliases:
                            ec.aliases.append(m_clean)
                            incoming_chars.append(ec)
                        break

            if not matched and is_valid_mention_token:
                # Apelido de um personagem conhecido (heurística de apelido/honorífico/"Apelido (Nome)")
                known = [c for c in [*incoming_chars, *existing_chars] if c.source != EntrySource.EXTRACTED]
                found = resolve_character(known, m_clean)
                if found is not None:
                    target = known[found[0]]
                    if can_add_alias([*incoming_chars, *existing_chars], found[1]):
                        target.aliases.append(found[1])
                    if not any(target is c for c in incoming_chars):
                        incoming_chars.append(target)
                    matched = True

            if not matched and is_valid_mention_token:
                # Novo personagem detectado apenas nas falas (ignora tokens curtos ou honoríficos isolados)
                incoming_chars.append(CharacterEntry(name=m_clean, source=EntrySource.EXTRACTED))

        merged_chars = mem_store.merge_characters(incoming_chars)

        # Estilo de fala observado nos episódios (artefatos antigos não têm o campo)
        observed_styles = [s for ep_art in episodes_extracts.values() if ep_art for s in ep_art.character_styles]
        if observed_styles:
            merged_chars = apply_character_styles(merged_chars, observed_styles)

        # Personagens extraídos em rodadas anteriores que são apelidos de outro viram aliases dele
        merged_chars = merge_nickname_characters(merged_chars)
        mem_store.save_characters(merged_chars)

        # 4. Consolidação de Glossário
        incoming_terms = []
        for ep_art in episodes_extracts.values():
            if ep_art and ep_art.terms:
                incoming_terms.extend(ep_art.terms)

        merged_glossary = sanitize_glossary(mem_store.merge_glossary(incoming_terms), merged_chars)
        mem_store.save_glossary(merged_glossary)

        # 5. Consolidação de História (story.yaml)
        if meta and meta.story:
            story = meta.story
        else:
            existing_story = mem_store.load_story()
            if existing_story is not None:
                story = existing_story
            else:
                title = meta.title if (meta and meta.title) else ctx.series.name
                story = StoryMemory(title=title)

        mem_store.save_story(story)

        # 6. Cálculo de Hashes
        char_hash = (
            hashlib.sha256(mem_store.characters_path.read_bytes()).hexdigest()
            if mem_store.characters_path.exists()
            else ""
        )
        glossary_hash = (
            hashlib.sha256(mem_store.glossary_path.read_bytes()).hexdigest() if mem_store.glossary_path.exists() else ""
        )
        story_hash = (
            hashlib.sha256(mem_store.story_path.read_bytes()).hexdigest() if mem_store.story_path.exists() else ""
        )

        # 7. Gravação do Artefato
        artifact = ConsolidatedMemoryArtifact(
            series_name=ctx.series.name,
            characters_count=len(merged_chars),
            glossary_count=len(merged_glossary),
            characters_hash=char_hash,
            glossary_hash=glossary_hash,
            story_hash=story_hash,
            glossary_terms=[e.term for e in merged_glossary],
        )
        ctx.output.json(artifact)


__all__ = ["ConsolidateMemoryStage"]
