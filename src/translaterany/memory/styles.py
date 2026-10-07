"""Consolidação do estilo de fala (speech_style) dos personagens a partir da extração de vários episódios."""

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


def _find_character(chars: list[CharacterEntry], name: str) -> int | None:
    key = _norm(name).lower()
    for idx, c in enumerate(chars):
        if key == _norm(c.name).lower() or key in {_norm(a).lower() for a in c.aliases}:
            return idx
    if is_valid_character_token(name):
        token_hits = [idx for idx, c in enumerate(chars) if key.strip(".,!?:;\"'") in character_tokens(c.name)]
        if len(token_hits) == 1:
            return token_hits[0]
    return None


def apply_character_styles(chars: Iterable[CharacterEntry], observed: Iterable[CharacterStyle]) -> list[CharacterEntry]:
    """Preenche `speech_style` dos personagens com o estilo mais frequente observado nos episódios.

    Nunca sobrescreve um estilo não vazio de personagem `user`/`metadata`; o `source` nunca muda.
    Nomes sem personagem correspondente (nome/alias ou token único) viram personagens extraídos.
    """
    result = [c.model_copy() for c in chars]
    candidates: dict[int, list[str]] = {}
    for item in observed:
        name, style = _norm(item.name), _norm(item.speech_style)
        if not style or not character_tokens(name):
            continue
        idx = _find_character(result, name)
        if idx is None:
            result.append(CharacterEntry(name=name, source=EntrySource.EXTRACTED))
            idx = len(result) - 1
        candidates.setdefault(idx, []).append(style)

    for idx, styles in candidates.items():
        c = result[idx]
        if c.speech_style and c.source != EntrySource.EXTRACTED:
            continue
        result[idx] = c.model_copy(update={"speech_style": pick_style(styles)})
    return result
