"""Memória de Tradução (TM) da série para reuso de linhas idênticas."""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


class TMEntrySource(StrEnum):
    USER = "user"
    AUTO = "auto"


class TMEntry(BaseModel):
    clean_text: str
    translation: str
    category: str = "dialogue"  # "dialogue", "sign", "song"
    source: TMEntrySource = TMEntrySource.AUTO
    occurrences: int = 1
    episodes: list[str] = Field(default_factory=list)


class TranslationMemoryDoc(BaseModel):
    entries: dict[str, TMEntry] = Field(default_factory=dict)


def normalize_tm_key(text: str) -> str:
    """Normaliza o texto para busca na TM (minúsculas e espaços colapsados)."""
    return re.sub(r"\s+", " ", text).strip().lower()


class TranslationMemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)

    def load(self) -> TranslationMemoryDoc:
        if not self.path.exists():
            return TranslationMemoryDoc()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = self._yaml.load(f)
            if not isinstance(data, dict):
                return TranslationMemoryDoc()
            entries_raw = data.get("entries", {})
            entries: dict[str, TMEntry] = {}
            for k, v in entries_raw.items():
                if isinstance(v, dict):
                    entries[k] = TMEntry.model_validate(v)
            return TranslationMemoryDoc(entries=entries)
        except Exception as exc:
            logger.warning("Falha ao ler memória de tradução %s: %s. Operando com TM vazia.", self.path, exc)
            return TranslationMemoryDoc()

    def save(self, doc: TranslationMemoryDoc) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        raw = {"entries": {k: v.model_dump(mode="json") for k, v in doc.entries.items()}}
        with open(tmp_path, "w", encoding="utf-8") as f:
            self._yaml.dump(raw, f)
        tmp_path.replace(self.path)


    def lookup(self, text: str, category: str, min_dialogue_chars: int = 15) -> str | None:
        key = normalize_tm_key(text)
        doc = self.load()
        if key not in doc.entries:
            return None
        entry = doc.entries[key]
        if category == "dialogue":
            if entry.source == TMEntrySource.USER or len(entry.clean_text) >= min_dialogue_chars:
                return entry.translation
            return None
        return entry.translation

    def record_translation(
        self,
        clean_text: str,
        translation: str,
        category: str,
        episode_key: str | None = None,
    ) -> None:
        if not clean_text or not translation:
            return
        key = normalize_tm_key(clean_text)
        doc = self.load()
        if key in doc.entries:
            existing = doc.entries[key]
            existing.occurrences += 1
            if episode_key and episode_key not in existing.episodes:
                existing.episodes.append(episode_key)
            if existing.source != TMEntrySource.USER:
                existing.translation = translation
                existing.category = category
        else:
            doc.entries[key] = TMEntry(
                clean_text=clean_text,
                translation=translation,
                category=category,
                source=TMEntrySource.AUTO,
                occurrences=1,
                episodes=[episode_key] if episode_key else [],
            )
        self.save(doc)
