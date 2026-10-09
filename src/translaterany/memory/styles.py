"""Consolidação do estilo de fala (speech_style) dos personagens a partir da extração de vários episódios."""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

from translaterany.memory.artifacts import CharacterStyle
from translaterany.memory.models import CharacterEntry, EntrySource

COMMON_HONORIFICS: frozenset[str] = frozenset(
    {
        "san",
        "kun",
        "chan",
        "sama",
        "sensei",
        "senpai",
        "dono",
        "shi",
        "tan",
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "lord",
        "lady",
    }
)


def is_valid_character_token(token: str) -> bool:
    """Verifica se um token é válido para correspondência heurística (ignora <= 2 chars e honoríficos)."""
    clean = token.strip(".,!?:;\"'").lower()
    return len(clean) > 2 and clean not in COMMON_HONORIFICS


def character_tokens(name: str) -> list[str]:
    """Extrai tokens válidos de um nome de personagem para correspondência heurística."""
    tokens = [t.strip(".,!?:;\"'").lower() for t in name.split()]
    return [t for t in tokens if len(t) > 2 and t not in COMMON_HONORIFICS]


def _norm(text: str) -> str:
    return " ".join(text.split())


def pick_style(candidates: Iterable[str]) -> str:
    """Estilo mais frequente entre os candidatos (empate: o mais longo); vazio se não houver nenhum."""
    counts: Counter[str] = Counter()
    original: dict[str, str] = {}
    for cand in candidates:
        clean = _norm(cand)
        if clean:
            counts[clean.lower()] += 1
            original.setdefault(clean.lower(), clean)
    if not counts:
        return ""
    best = max(counts, key=lambda k: (counts[k], len(k)))
    return original[best]


MIN_NICKNAME_LENGTH = 4  # menor forma aceita na heurística de apelido ("Yuki" ainda passa, "Mik" não)
_PARENTHETICAL_NAME = re.compile(r"^(?P<outer>[^()]*?)\s*\((?P<inner>[^()]+)\)\s*$")


def fold(text: str) -> str:
    """Forma comparável: sem diacríticos, minúscula e com espaços normalizados."""
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().split())


def strip_honorifics(name: str) -> str:
    """Remove honoríficos soltos ou ligados por hífen ("Daru-kun", "Dr. Sato" -> "Daru", "Sato")."""
    parts = [p for token in name.split() for p in token.split("-")]
    kept = [p for p in parts if p.strip(".,!?:;\"'").lower() not in COMMON_HONORIFICS]
    return " ".join(kept)


def _nickname_key(text: str) -> str:
    """Chave para a heurística de apelido: dobra L/R (romanização japonesa: "Ruka" ~ "Luka")."""
    return fold(text).replace("l", "r")


def _is_nickname_of(nick: str, form: str) -> bool:
    """Uma forma contém a outra e a menor tem >= 4 letras e pelo menos 2/3 da maior ("Rukako" ~ "Luka")."""
    short, long_ = sorted((nick, form), key=len)
    return len(short) >= MIN_NICKNAME_LENGTH and 3 * len(short) >= 2 * len(long_) and short in long_


def _forms(c: CharacterEntry) -> list[str]:
    """Nome e aliases inteiros mais seus tokens válidos, para comparar apelidos."""
    forms = [c.name, *c.aliases]
    return [*forms, *(t for f in forms for t in character_tokens(f))]


def _unique(hits: list[int]) -> int | None:
    return hits[0] if len(hits) == 1 else None


def _resolve_plain(chars: list[CharacterEntry], name: str) -> int | None:
    """Resolve um nome sem parênteses: nome/alias exato, token único do nome, depois heurística de apelido."""
    for query in dict.fromkeys(q for q in (name, strip_honorifics(name)) if fold(q)):
        key = fold(query)
        for idx, c in enumerate(chars):
            if key == fold(c.name) or key in {fold(a) for a in c.aliases}:
                return idx
        if is_valid_character_token(query):
            token = key.strip(".,!?:;\"'")
            hit = _unique([i for i, c in enumerate(chars) if token in [fold(t) for t in character_tokens(c.name)]])
            if hit is not None:
                return hit
    for query in dict.fromkeys(q for q in (name, strip_honorifics(name)) if fold(q)):
        nick = _nickname_key(query)
        hits = [i for i, c in enumerate(chars) if any(_is_nickname_of(nick, _nickname_key(f)) for f in _forms(c))]
        if len(hits) == 1:
            return hits[0]
    return None


def resolve_character(chars: list[CharacterEntry], name: str) -> tuple[int, str] | None:
    """Personagem existente a que `name` se refere e a forma de apelido a registrar como alias.

    Ordem: nome/alias exato (sem caixa/diacríticos), nome sem honorífico, token único do nome, heurística de
    apelido (um contém o outro, com comprimento mínimo) e, para "Apelido (Nome Completo)", cada parte.
    Retorna None se nada casar ou se houver mais de um candidato.
    """
    clean = _norm(name)
    idx = _resolve_plain(chars, clean)
    if idx is not None:
        return idx, clean
    paren = _PARENTHETICAL_NAME.match(clean)
    if paren:
        outer, inner = paren.group("outer").strip(), paren.group("inner").strip()
        for part, nickname in ((inner, outer), (outer, outer)):
            idx = _resolve_plain(chars, part) if part else None
            if idx is not None:
                return idx, nickname
    return None


def find_character(chars: list[CharacterEntry], name: str) -> int | None:
    found = resolve_character(chars, name)
    return found[0] if found else None


def can_add_alias(chars: list[CharacterEntry], nickname: str) -> bool:
    """O apelido é utilizável como alias: tem token válido e não repete o nome/alias de nenhum personagem."""
    key = fold(nickname)
    if not key or not character_tokens(nickname):
        return False
    return not any(key == fold(f) for c in chars for f in (c.name, *c.aliases))


def add_alias(chars: list[CharacterEntry], idx: int, nickname: str) -> bool:
    """Registra o apelido como alias de chars[idx] (sem alterar o objeto original), se não houver colisão."""
    if not can_add_alias(chars, nickname):
        return False
    target = chars[idx]
    chars[idx] = target.model_copy(update={"aliases": [*target.aliases, _norm(nickname)]})
    return True


def apply_character_styles(chars: Iterable[CharacterEntry], observed: Iterable[CharacterStyle]) -> list[CharacterEntry]:
    """Preenche `speech_style` dos personagens com o estilo mais frequente observado nos episódios.

    Nunca sobrescreve um estilo não vazio de personagem `user`/`metadata`; o `source` nunca muda.
    Nomes que são apelidos de um personagem existente (nome/alias, token único, honorífico ou heurística de
    apelido) entram como alias dele; só o que não casa com ninguém vira personagem extraído.
    """
    result = [c.model_copy() for c in chars]
    candidates: dict[int, list[str]] = {}
    for item in observed:
        name, style = _norm(item.name), _norm(item.speech_style)
        if not style or not character_tokens(name):
            continue
        found = resolve_character(result, name)
        if found is None:
            result.append(CharacterEntry(name=name, source=EntrySource.EXTRACTED))
            idx = len(result) - 1
        else:
            idx = found[0]
            add_alias(result, idx, found[1])  # apelido usado no diálogo: vira alias do personagem
        candidates.setdefault(idx, []).append(style)

    for idx, styles in candidates.items():
        c = result[idx]
        if c.speech_style and c.source != EntrySource.EXTRACTED:
            continue
        result[idx] = c.model_copy(update={"speech_style": pick_style(styles)})
    return result
