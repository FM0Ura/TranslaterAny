"""Limpeza de personagens extraídos que, na verdade, são apelidos de outro personagem da série."""

import re

from translaterany.memory.models import CharacterEntry, EntrySource
from translaterany.memory.styles import add_alias, resolve_character

_NAME_LIST_SPLIT = re.compile(r"\s*(?:,|;|&|\be\b|\band\b)\s*")


def _lists_several_characters(pool: list[CharacterEntry], name: str) -> bool:
    """True se o nome é uma enumeração ("A, B") cujas partes casam com personagens diferentes."""
    parts = [p for p in _NAME_LIST_SPLIT.split(name) if p.strip()]
    if len(parts) < 2:
        return False
    hits = {found[0] for p in parts if (found := resolve_character(pool, p)) is not None}
    return len(hits) >= 2


def merge_nickname_characters(chars: list[CharacterEntry]) -> list[CharacterEntry]:
    """Funde personagens extraídos que são apelidos de um personagem `user`/`metadata` (idempotente).

    O nome e os aliases do extraído viram aliases do alvo (quando não colidem com outro personagem) e a entrada
    extraída some. Personagens `user`/`metadata` só recebem aliases; extraídos sem alvo único ficam como estão.
    """
    result = [c.model_copy() for c in chars]
    for extracted in [c for c in result if c.source == EntrySource.EXTRACTED]:
        pool_idx = [i for i, c in enumerate(result) if c.source != EntrySource.EXTRACTED]
        pool = [result[i] for i in pool_idx]
        found = resolve_character(pool, extracted.name)
        if found is None and not _lists_several_characters(pool, extracted.name):
            continue
        result = [c for c in result if c is not extracted]  # sai antes, para o apelido não colidir com ele mesmo
        if found is not None:
            target = next(i for i, c in enumerate(result) if c is pool[found[0]])
            for nickname in (found[1], *extracted.aliases):
                add_alias(result, target, nickname)
    return result
