"""Casamento de termos/nomes da memória da série com um texto (palavra inteira, sem diferenciar caixa)."""

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from translaterany.memory.models import CharacterEntry, GlossaryEntry

if TYPE_CHECKING:
    from translaterany.pipeline.artifacts import ArtifactStore


def _term_pattern(term: str) -> re.Pattern[str]:
    prefix = r"\b" if re.match(r"^\w", term) else ""
    suffix = r"\b" if re.search(r"\w$", term) else ""
    return re.compile(rf"{prefix}{re.escape(term)}{suffix}", re.IGNORECASE)


def matches_term(term: str, text: str) -> bool:
    if not term:
        return False
    return bool(_term_pattern(term).search(text))


def term_spans(term: str, text: str) -> list[tuple[int, int]]:
    """Intervalos (início, fim) de cada ocorrência do termo no texto, com a mesma semântica de matches_term."""
    if not term:
        return []
    return [m.span() for m in _term_pattern(term).finditer(text)]


def glossary_matches(glossary: Iterable[GlossaryEntry], text: str) -> list[tuple[GlossaryEntry, list[str]]]:
    """Entradas do glossário presentes no texto, com as formas (termo/aliases) que casaram em algum trecho que vale.

    Resolução do mais longo para o mais curto, sem sobreposição (igual à do GlossaryProtector): uma forma que só
    casa dentro de uma entrada mais longa ("Gate" em "Steins Gate") não conta como menção da entrada curta.
    Trechos idênticos de entradas diferentes coexistem: nenhum engole o outro.
    """
    entries = list(glossary)
    candidates = [
        (start, end, i, form)
        for i, entry in enumerate(entries)
        for form in dict.fromkeys((entry.term, *entry.aliases))
        for start, end in term_spans(form, text)
    ]
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken: list[tuple[int, int]] = []
    forms: dict[int, list[str]] = {}
    for start, end, i, form in candidates:
        if (start, end) in taken or not any(start < t_end and t_start < end for t_start, t_end in taken):
            taken.append((start, end))
            if form not in forms.setdefault(i, []):
                forms[i].append(form)
    return [(entries[i], forms[i]) for i in sorted(forms)]


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
