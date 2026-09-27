"""Redistribuição de frases traduzidas em unidades compostas de volta para os eventos originais."""

from __future__ import annotations

import re

from translaterany.subtitles.merge import CompositeUnit


def _find_split_points(text: str, durations: list[int]) -> list[int]:
    n = len(durations)
    if n <= 1:
        return []
    total_dur = sum(durations) or n
    length = len(text)

    # Identifica spans de marcadores inline ⟦n⟧
    marker_spans = [m.span() for m in re.finditer(r"⟦\d+⟧", text)]

    def inside_marker(pos: int) -> bool:
        return any(s < pos < e for s, e in marker_spans)

    # Identifica posições de início de whitespace (cortes limpos entre palavras)
    spaces: list[int] = []
    for m in re.finditer(r"\s+", text):
        pos = m.start()
        if not inside_marker(pos) and 0 < pos < length:
            spaces.append(pos)

    cuts: list[int] = []
    cum_dur = 0
    prev_cut = 0
    for k in range(n - 1):
        cum_dur += durations[k]
        target = round((cum_dur / total_dur) * length)

        valid_spaces = [s for s in spaces if s > prev_cut]
        if valid_spaces:

            def score(s: int) -> float:
                dist = abs(s - target)
                prefix = text[:s].rstrip()
                # Pontuação de cláusula ou forte ganha prioridade
                if prefix.endswith(("...", "…", ".", "!", "?", "—")):
                    penalty = 0.8
                elif prefix.endswith((",", ";", ":", "-")):
                    penalty = 1.0
                else:
                    penalty = 2.5
                return dist * penalty

            best_s = min(valid_spaces, key=score)
            cuts.append(best_s)
            prev_cut = best_s
        else:
            # Fallback se não houver espaços suficientes
            best_pos = min(
                (p for p in range(prev_cut + 1, length) if not inside_marker(p)),
                key=lambda p: abs(p - target),
                default=prev_cut + 1,
            )
            cuts.append(best_pos)
            prev_cut = best_pos

    return cuts


def redistribute_composite_unit(comp: CompositeUnit, translated_text: str) -> dict[str, str]:
    """Divide a tradução de uma unidade composta proporcionalmente à duração dos eventos originais."""
    unit_ids = comp.unit_ids
    if len(unit_ids) <= 1:
        return {unit_ids[0]: translated_text}

    cuts = _find_split_points(translated_text, comp.durations_ms)
    parts: list[str] = []
    curr = 0
    for cut in cuts:
        parts.append(translated_text[curr:cut].strip())
        m = re.match(r"\s+", translated_text[cut:])
        space_len = len(m.group(0)) if m else 0
        curr = cut + space_len
    parts.append(translated_text[curr:].strip())

    result: dict[str, str] = {}
    for i, uid in enumerate(unit_ids):
        result[uid] = parts[i] if i < len(parts) else ""
    return result
