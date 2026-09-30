"""Quebra de linha e orçamento de caracteres para legendas legíveis (limites do [checks])."""

import re

from translaterany.subtitles.segments import MARKER_RE

_BREAK = re.compile(r"\s*\\[Nn]\s*")
_SPACES = re.compile(r" {2,}")
_PUNCT_END = (",", ".", "!", "?", ";", ":", "…")


def flatten_breaks(text: str) -> str:
    """Junta as linhas de uma fala: o modelo traduz a frase inteira e a quebra é refeita depois."""
    return _SPACES.sub(" ", _BREAK.sub(" ", text)).strip()


def _visible_len(text: str) -> int:
    return len(MARKER_RE.sub("", text))


def wrap_line(text: str, max_cpl: int) -> str:
    """Uma linha se couber; senão duas, no espaço mais equilibrado — preferindo a de baixo maior
    (pirâmide) e o corte depois de pontuação. Conta só caracteres visíveis (sem marcadores ⟦n⟧)."""
    flat = flatten_breaks(text)
    if _visible_len(flat) <= max_cpl:
        return flat
    best: tuple[float, int] | None = None
    for i, ch in enumerate(flat):
        if ch != " ":
            continue
        top, bottom = _visible_len(flat[:i]), _visible_len(flat[i + 1 :])
        score = abs(top - bottom) + (0 if top <= bottom else 3) + (100 if max(top, bottom) > max_cpl else 0)
        if flat[:i].rstrip().endswith(_PUNCT_END):
            score -= 4
        if best is None or score < best[0]:
            best = (score, i)
    if best is None:
        return flat
    cut = best[1]
    return f"{flat[:cut]}\\N{flat[cut + 1 :]}"


def char_budget(duration_ms: int, *, max_cps: float, max_cpl: int) -> int | None:
    """Caracteres que cabem na duração da fala (máximo: duas linhas cheias). None sem duração."""
    if duration_ms <= 0:
        return None
    return min(int(max_cps * duration_ms / 1000), 2 * max_cpl)
