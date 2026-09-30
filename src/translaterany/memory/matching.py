"""Casamento de termos/nomes da memória da série com um texto (palavra inteira, sem diferenciar caixa)."""

import re
from collections.abc import Iterable

from translaterany.memory.models import CharacterEntry, GlossaryEntry


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
    chars = [c for c in characters if any(matches_term(n, text) for n in (c.name, *c.aliases))]
    return terms, chars
