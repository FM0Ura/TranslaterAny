"""Serviço para gerenciamento e edição da memória de séries (personagens, glossário, história)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field

from translaterany.config.loader import default_data_dir
from translaterany.memory.models import CharacterEntry, GlossaryEntry, StoryMemory
from translaterany.memory.store import MemoryStore


class MemoryDoc(BaseModel):
    characters: list[CharacterEntry] = Field(default_factory=list)
    glossary: dict[str, GlossaryEntry] = Field(default_factory=dict)
    story: StoryMemory | None = None


class MemoryService:
    """Encapsula operações de leitura e persistência em YAML via MemoryStore."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()

    def _get_store(self, series_key: str) -> MemoryStore:
        series_dir = self.data_dir / "series" / series_key
        return MemoryStore(series_dir)

    def load_memory(self, series_key: str) -> MemoryDoc:
        store = self._get_store(series_key)
        return MemoryDoc(
            characters=store.load_characters(),
            glossary=store.load_glossary(),
            story=store.load_story(),
        )

    def save_characters(self, series_key: str, characters: list[CharacterEntry]) -> None:
        store = self._get_store(series_key)
        store.save_characters(characters)

    def add_character(self, series_key: str, character: CharacterEntry) -> None:
        store = self._get_store(series_key)
        chars = store.load_characters()
        chars = [c for c in chars if c.name.lower() != character.name.lower()]
        chars.append(character)
        store.save_characters(chars)

    def delete_character(self, series_key: str, name: str) -> bool:
        store = self._get_store(series_key)
        chars = store.load_characters()
        filtered = [c for c in chars if c.name.lower() != name.strip().lower()]
        if len(filtered) != len(chars):
            store.save_characters(filtered)
            return True
        return False

    def save_glossary(
        self, series_key: str, glossary: dict[str, GlossaryEntry] | Iterable[GlossaryEntry]
    ) -> None:
        store = self._get_store(series_key)
        store.save_glossary(glossary)

    def add_glossary_term(self, series_key: str, term: GlossaryEntry) -> None:
        store = self._get_store(series_key)
        existing = store.load_glossary()
        existing[term.term] = term
        store.save_glossary(existing)

    def delete_glossary_term(self, series_key: str, term: str) -> bool:
        store = self._get_store(series_key)
        existing = store.load_glossary()
        term_lower = term.strip().lower()
        key_to_delete = None
        for k in existing:
            if k.lower() == term_lower:
                key_to_delete = k
                break
        if key_to_delete is not None:
            del existing[key_to_delete]
            store.save_glossary(existing)
            return True
        return False

    def save_story(self, series_key: str, story: StoryMemory) -> None:
        store = self._get_store(series_key)
        store.save_story(story)
