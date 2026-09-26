"""Módulo de memória da série (metadados, personagens, glossário e história)."""

from translaterany.memory.anilist import AniListClient, AniListMatch
from translaterany.memory.artifacts import (
    ConsolidatedMemoryArtifact,
    ExtractTermsArtifact,
    MetadataArtifact,
)
from translaterany.memory.jikan import JikanClient
from translaterany.memory.models import (
    CharacterEntry,
    CharacterRole,
    EntrySource,
    EpisodeSynopsis,
    Gender,
    GlossaryCategory,
    GlossaryEntry,
    StoryMemory,
)
from translaterany.memory.store import MemoryStore

__all__ = [
    "AniListClient",
    "AniListMatch",
    "CharacterEntry",
    "CharacterRole",
    "ConsolidatedMemoryArtifact",
    "EntrySource",
    "EpisodeSynopsis",
    "ExtractTermsArtifact",
    "Gender",
    "GlossaryCategory",
    "GlossaryEntry",
    "JikanClient",
    "MemoryStore",
    "MetadataArtifact",
    "StoryMemory",
]

