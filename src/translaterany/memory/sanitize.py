"""Higienização do glossário consolidado: aliases colidentes e variantes quase idênticas de um mesmo termo.

O glossário extraído por LLM acumula aliases que apontam para outra entrada ou para um personagem
(ex.: o alias de uma entrada ser o termo de outra). Como a checagem `glossary` bloqueia o gate de
tradução, essas colisões geram falsos positivos. Aqui as colisões são resolvidas de forma
determinística e idempotente; entradas `user` nunca são alteradas ou removidas.
"""

from collections.abc import Iterable

from translaterany.memory.models import CharacterEntry, EntrySource, GlossaryEntry
from translaterany.memory.store import PRECEDENCE_RANK


def _key(text: str) -> str:
    return " ".join(text.split()).lower()


def _rank(entry: GlossaryEntry) -> int:
    return PRECEDENCE_RANK.get(entry.source, 1)


def _is_variant(longer: str, shorter: str) -> bool:
    """True se `longer` é `shorter` seguido de complemento entre parênteses ou após vírgula."""
    long_k, short_k = _key(longer), _key(shorter)
    if long_k == short_k or not long_k.startswith(short_k):
        return False
    return long_k[len(short_k) :].lstrip().startswith(("(", ","))


def _dedupe_aliases(aliases: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for alias in aliases:
        clean = alias.strip()
        if clean and _key(clean) not in seen:
            seen[_key(clean)] = clean
    return list(seen.values())


def _drop_duplicates_of_protected(entries: list[GlossaryEntry]) -> list[GlossaryEntry]:
    """Remove entradas extraídas cujo termo já é termo/alias de uma entrada de precedência maior."""
    protected: set[str] = set()
    for e in entries:
        if e.source != EntrySource.EXTRACTED:
            protected.add(_key(e.term))
            protected.update(_key(a) for a in e.aliases)
    return [e for e in entries if e.source != EntrySource.EXTRACTED or _key(e.term) not in protected]


def _merge_variants(entries: list[GlossaryEntry]) -> list[GlossaryEntry]:
    """Funde variantes extraídas ("X (rascunho)", "X, 2ª edição") na entrada extraída de termo mais curto."""
    extracted = [e for e in entries if e.source == EntrySource.EXTRACTED]
    root_of: dict[int, GlossaryEntry] = {}
    for e in extracted:
        candidates = [r for r in extracted if r is not e and r.category == e.category and _is_variant(e.term, r.term)]
        if candidates:
            root_of[id(e)] = min(candidates, key=lambda r: len(_key(r.term)))

    extra_aliases: dict[int, list[str]] = {}
    extra_notes: dict[int, str | None] = {}
    for e in extracted:
        root = root_of.get(id(e))
        if root is None:
            continue
        extra_aliases.setdefault(id(root), []).extend([e.term, *e.aliases])
        if root.notes is None and e.notes:
            extra_notes.setdefault(id(root), e.notes)

    result: list[GlossaryEntry] = []
    for e in entries:
        if id(e) in root_of:
            continue
        if id(e) in extra_aliases:
            e = e.model_copy(
                update={
                    "aliases": [*e.aliases, *extra_aliases[id(e)]],
                    "notes": e.notes if e.notes is not None else extra_notes.get(id(e)),
                }
            )
        result.append(e)
    return result


def sanitize_glossary(entries: Iterable[GlossaryEntry], characters: Iterable[CharacterEntry]) -> list[GlossaryEntry]:
    """Remove colisões de aliases e funde variantes quase idênticas de termos extraídos.

    - alias igual ao próprio termo: removido;
    - alias que é termo de outra entrada, ou nome/alias de personagem: removido;
    - alias compartilhado entre entradas: fica só com a de maior precedência (empate: a primeira);
    - termos extraídos que são variante entre parênteses/vírgula de outro (mesma categoria): fundidos no mais curto;
    - entradas `user` nunca são alteradas; extraídas duplicadas de termo/alias protegido são descartadas.
    """
    items = [e.model_copy() for e in entries]
    items = _drop_duplicates_of_protected(items)
    items = _merge_variants(items)

    char_forms = {_key(form) for c in characters for form in (c.name, *c.aliases) if form.strip()}
    term_owner: dict[str, int] = {}
    for idx, e in enumerate(items):
        term_owner.setdefault(_key(e.term), idx)

    alias_owner: dict[str, int] = {}
    for idx, e in enumerate(items):
        for alias in e.aliases:
            k = _key(alias)
            owner = alias_owner.get(k)
            if owner is None or _rank(e) > _rank(items[owner]):
                alias_owner[k] = idx

    result: list[GlossaryEntry] = []
    for idx, e in enumerate(items):
        if e.source == EntrySource.USER:
            result.append(e)
            continue
        kept: list[str] = []
        for alias in _dedupe_aliases(e.aliases):
            k = _key(alias)
            if k == _key(e.term) or k in char_forms:
                continue
            if term_owner.get(k, idx) != idx or alias_owner.get(k) != idx:
                continue
            kept.append(alias)
        result.append(e.model_copy(update={"aliases": kept}))
    return result
