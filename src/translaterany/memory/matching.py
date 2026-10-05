"""Casamento de termos/nomes da memória da série com um texto (palavra inteira, sem diferenciar caixa)."""

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from translaterany.memory.models import CharacterEntry, GlossaryEntry

if TYPE_CHECKING:
    from translaterany.pipeline.artifacts import ArtifactStore


def matches_term(term: str, text: str) -> bool:
    if not term:
        return False
    prefix = r"\b" if re.match(r"^\w", term) else ""
    suffix = r"\b" if re.search(r"\w$", term) else ""
    return bool(re.search(rf"{prefix}{re.escape(term)}{suffix}", text, re.IGNORECASE))


def select_for_text(
    glossary: Iterable[GlossaryEntry], characters: Iterable[CharacterEntry], text: str
) -> tuple[list[GlossaryEntry], list[CharacterEntry]]:
    """Entradas do glossário e personagens mencionados no texto (filtro por episódio)."""
    terms = [e for e in glossary if any(matches_term(t, text) for t in (e.term, *e.aliases))]
    chars = []
    for c in characters:
        forms = [c.name, *c.aliases]
        for part in c.name.split():
            cleaned = part.strip()
            if len(cleaned) >= 3 and cleaned not in forms:
                forms.append(cleaned)
        if any(matches_term(n, text) for n in forms):
            chars.append(c)
    return terms, chars


def load_memory_for_text(
    store: ArtifactStore | None, series_key: str, text: str
) -> tuple[list[GlossaryEntry], list[CharacterEntry]]:
    """Glossário e personagens da série mencionados no texto (filtro por episódio)."""
    if store is None:
        return [], []
    mem_dir = store.series_dir(series_key) / "memory"
    if not mem_dir.exists():
        return [], []
    from translaterany.memory.store import MemoryStore  # import tardio: evita ciclo memory <-> pipeline

    mem = MemoryStore(mem_dir)
    return select_for_text(mem.load_glossary().values(), mem.load_characters(), text)


def load_all_characters(store: ArtifactStore | None, series_key: str) -> list[CharacterEntry]:
    """Todos os personagens da série a partir do memory store."""
    if store is None:
        return []
    mem_dir = store.series_dir(series_key) / "memory"
    if not mem_dir.exists():
        return []
    from translaterany.memory.store import MemoryStore  # import tardio: evita ciclo memory <-> pipeline

    mem = MemoryStore(mem_dir)
    return mem.load_characters()

