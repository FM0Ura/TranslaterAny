"""Redistribuição de frases traduzidas em unidades compostas de volta para os eventos originais."""

from __future__ import annotations

import re

from translaterany.subtitles.merge import CompositeUnit
from translaterany.subtitles.segments import MARKER_RE

# Separador de palavras: espaços e quebras ASS literais (\N / \n)
_SEP = re.compile(r"(?:\s|\\[Nn])+")
_HARD_BREAK = re.compile(r"\n|\\[Nn]")

_STRONG_END = ("...", "…", ".", "!", "?", "—", "”", "\"")
_CLAUSE_END = (",", ";", ":", "-", "–")

# Palavras funcionais (pt/es/en/fr/it): um evento não deve terminar nelas, pois a frase fica pendurada
_FUNCTION_WORDS = frozenset(
    """a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para pra
    com sem sob sobre ao aos à às e ou mas que se como quando porque pois nem até e/ou seu sua meu minha
    the an of to in on at by for with and or but that if as from into
    el la los las un una unos unas del al y o pero porque cuando con sin
    le les des du et ou mais que
    il lo gli i di da e ma che""".split()
)
# Conectores que não devem abrir um evento quando o corte caiu no meio da oração
_CONNECTORS = frozenset(
    "e ou mas que se como porque pois nem quando and or but that if y pero porque et ou mais che ma".split()
)

_COST_PER_PERCENT = 1.0  # desvio da proporção de duração, por ponto percentual
_COST_NO_PUNCT = 25.0  # corte no meio da oração
_COST_CLAUSE = 6.0  # corte depois de vírgula, ponto e vírgula, dois-pontos
_BONUS_LINE_BREAK = 8.0  # o modelo já separou a frase em linhas
_COST_DANGLING_END = 30.0
_COST_CONNECTOR_START = 8.0
_COST_OPEN_PAREN = 100.0
_COST_PER_CHAR_OVER_CPL = 2.0
_COST_PER_CHAR_OVER_CPS = 0.5


def _visible_len(text: str) -> int:
    return len(MARKER_RE.sub("", text))


def _bare(word: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", word.lower())


def _split_words(text: str) -> tuple[list[tuple[int, int]], list[bool]]:
    """Posições (início, fim) de cada palavra e, para cada separador entre elas, se é quebra de linha."""
    spans: list[tuple[int, int]] = []
    hard: list[bool] = []
    pos = 0
    for m in _SEP.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
            hard.append(bool(_HARD_BREAK.search(m.group(0))))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
        hard.append(False)
    return spans, hard[: max(len(spans) - 1, 0)]


def _boundary_cost(words: list[str], hard: list[bool], j: int) -> float:
    """Custo de terminar um evento na palavra j (e começar o próximo em j+1)."""
    last, nxt = words[j], words[j + 1]
    if last.endswith(_STRONG_END):
        cost = 0.0
    elif last.endswith(_CLAUSE_END):
        cost = _COST_CLAUSE
    else:
        cost = _COST_NO_PUNCT
        if _bare(last) in _FUNCTION_WORDS:
            cost += _COST_DANGLING_END
        if _bare(nxt) in _CONNECTORS:
            cost += _COST_CONNECTOR_START
    if hard[j]:
        cost -= _BONUS_LINE_BREAK
    return cost


def _split_indices(
    words: list[str],
    hard: list[bool],
    durations: list[int],
    max_cpl: int,
    max_cps: float,
    max_lines: int,
) -> list[int]:
    """Índices (da última palavra de cada evento, exceto o último) que minimizam o custo total."""
    n, w = len(durations), len(words)
    total_dur = sum(durations) or n
    lens = [_visible_len(x) for x in words]
    prefix = [0]
    for ln in lens:
        prefix.append(prefix[-1] + ln + 1)
    total_len = prefix[-1] - 1 or 1
    parens = [0]
    for x in words:
        parens.append(parens[-1] + x.count("(") - x.count(")"))

    def part_cost(a: int, b: int, k: int) -> float:
        """Palavras a..b-1 no evento k: orçamento de caracteres por linha e por segundo."""
        chars = prefix[b] - prefix[a] - 1
        cost = max(0, chars - max_cpl * max_lines) * _COST_PER_CHAR_OVER_CPL
        budget = max_cps * (durations[k] / 1000)
        return cost + max(0.0, chars - budget) * _COST_PER_CHAR_OVER_CPS

    targets, cum = [], 0
    for d in durations[:-1]:
        cum += d
        targets.append(cum / total_dur)

    inf = float("inf")
    # best[k][j]: custo mínimo com o corte k terminando na palavra j; prev guarda o corte anterior
    best = [[inf] * w for _ in range(n)]
    prev = [[-1] * w for _ in range(n)]
    for k in range(n - 1):
        lo = k  # cada evento anterior precisa de ao menos uma palavra
        for j in range(lo, w - (n - 1 - k)):
            cut_ratio = (prefix[j + 1] - 1) / total_len
            cost = abs(cut_ratio - targets[k]) * 100 * _COST_PER_PERCENT
            cost += _boundary_cost(words, hard, j)
            if parens[j + 1] > 0:
                cost += _COST_OPEN_PAREN
            if k == 0:
                best[0][j] = cost + part_cost(0, j + 1, 0)
                continue
            for i in range(k - 1, j):
                if best[k - 1][i] == inf:
                    continue
                total = best[k - 1][i] + cost + part_cost(i + 1, j + 1, k)
                if total < best[k][j]:
                    best[k][j], prev[k][j] = total, i
    last = min(
        range(n - 2, w - 1),
        key=lambda j: best[n - 2][j] + part_cost(j + 1, w, n - 1),
    )
    cuts = [last]
    for k in range(n - 2, 0, -1):
        cuts.append(prev[k][cuts[-1]])
    return cuts[::-1]


def redistribute_composite_unit(
    comp: CompositeUnit,
    translated_text: str,
    *,
    max_cpl: int = 42,
    max_cps: float = 17.0,
    max_lines: int = 2,
) -> dict[str, str]:
    """Divide a tradução de uma unidade composta entre os eventos originais.

    Corta preferencialmente em pontuação (ponto, reticências, vírgula), perto do ponto proporcional à
    duração dos eventos; nunca no meio de uma palavra ou marcador e evitando terminar um evento numa
    palavra funcional. Se o modelo já separou a frase em uma linha por evento, usa as linhas.
    """
    unit_ids = comp.unit_ids
    if len(unit_ids) <= 1:
        return {unit_ids[0]: translated_text}
    n = len(unit_ids)
    durations = [*comp.durations_ms, *([1000] * n)][:n]

    spans, hard = _split_words(translated_text)
    parts: list[str] = [""] * n
    if len(spans) < n:
        # menos palavras que eventos: uma palavra por evento, na ordem
        for i, (s, e) in enumerate(spans):
            parts[i] = translated_text[s:e]
    else:
        lines = [ln.strip() for ln in re.split(r"\s*(?:\n|\\[Nn])\s*", translated_text) if ln.strip()]
        if len(lines) == n:
            parts = lines
        else:
            words = [translated_text[s:e] for s, e in spans]
            cuts = _split_indices(words, hard, durations, max_cpl, max_cps, max_lines)
            start = 0
            for k, cut in enumerate([*cuts, len(spans) - 1]):
                parts[k] = translated_text[spans[start][0] : spans[cut][1]]
                start = cut + 1
    return {uid: parts[i].strip() for i, uid in enumerate(unit_ids)}
