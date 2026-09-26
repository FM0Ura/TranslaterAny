"""Módulo de memória da série (metadados, personagens, glossário e história)."""

from translaterany.memory.artifacts import (
    ConsolidatedMemoryArtifact,
    ExtractTermsArtifact,
    MetadataArtifact,
)
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

__all__ = [
    "CharacterEntry",
    "CharacterRole",
    "ConsolidatedMemoryArtifact",
    "EntrySource",
    "EpisodeSynopsis",
    "ExtractTermsArtifact",
    "Gender",
    "GlossaryCategory",
    "GlossaryEntry",
    "MetadataArtifact",
    "StoryMemory",
]
