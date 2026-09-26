"""Modelos de dados para memória da série (personagens, glossário e história)."""

import hashlib
from enum import StrEnum

from pydantic import BaseModel, Field


class EntrySource(StrEnum):
    USER = "user"
    METADATA = "metadata"
    EXTRACTED = "extracted"


class CharacterRole(StrEnum):
    MAIN = "main"
    SUPPORTING = "supporting"
    BACKGROUND = "background"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class CharacterEntry(BaseModel):
    name: str
    native_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    gender: Gender = Gender.UNKNOWN
    role: CharacterRole = CharacterRole.SUPPORTING
    speech_style: str | None = None
    notes: str | None = None
    source: EntrySource = EntrySource.EXTRACTED


class GlossaryCategory(StrEnum):
    NAME = "name"
    PLACE = "place"
    TECHNIQUE = "technique"
    OBJECT = "object"
    ORGANIZATION = "org"
    GENERAL = "general"


class GlossaryEntry(BaseModel):
    term: str
    translation: str
    category: GlossaryCategory = GlossaryCategory.GENERAL
    keep_original: bool = False
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None
    source: EntrySource = EntrySource.EXTRACTED

    def content_hash(self) -> str:
        """Hash do conteúdo relevante da entrada para detecção de staleness."""
        data = f"{self.term}|{self.translation}|{self.category}|{self.keep_original}|{','.join(sorted(self.aliases))}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]


class EpisodeSynopsis(BaseModel):
    episode_key: str
    number: int
    title: str | None = None
    synopsis: str = ""


class StoryMemory(BaseModel):
    title: str
    romaji_title: str | None = None
    native_title: str | None = None
    year: int | None = None
    synopsis: str = ""
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    episodes: dict[str, EpisodeSynopsis] = Field(default_factory=dict)
