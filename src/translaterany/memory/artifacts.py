"""Artefatos gerados pelas etapas de memória do pipeline."""

from pydantic import BaseModel, Field

from translaterany.memory.models import CharacterEntry, GlossaryEntry, StoryMemory


class MetadataArtifact(BaseModel):
    matched: bool
    anilist_id: int | None = None
    mal_id: int | None = None
    title: str = ""
    characters: list[CharacterEntry] = Field(default_factory=list)
    story: StoryMemory | None = None


class CharacterStyle(BaseModel):
    """Estilo de fala de um personagem observado em um episódio (descrição curta em PT-BR)."""

    name: str
    speech_style: str


class ExtractTermsArtifact(BaseModel):
    episode_key: str
    terms: list[GlossaryEntry] = Field(default_factory=list)
    character_mentions: list[str] = Field(default_factory=list)
    character_styles: list[CharacterStyle] = Field(default_factory=list)  # ausente em artefatos antigos


class ConsolidatedMemoryArtifact(BaseModel):
    series_name: str
    characters_count: int
    glossary_count: int
    characters_hash: str
    glossary_hash: str
    story_hash: str
    glossary_terms: list[str] = Field(default_factory=list)
