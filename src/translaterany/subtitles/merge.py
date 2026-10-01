"""Fusão de frases de diálogo partidas entre múltiplos eventos consecutivos."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from translaterany.subtitles.classify import UnitClass
from translaterany.subtitles.normalize import NormalizedDoc, Unit

_CLEAN_RE = re.compile(r"⟦\d+⟧")
_TERMINAL_PUNCT = (".", "!", "?", "—")


class CompositeUnit(BaseModel):
    composite_id: str
    unit_ids: list[str]
    durations_ms: list[int]
    clean_text: str
    text_with_markers: str
    speaker: str = "Unknown"


class MergedUnitsDoc(BaseModel):
    units: list[CompositeUnit] = Field(default_factory=list)
    merged_count: int = 0


def _clean(text: str) -> str:
    return _CLEAN_RE.sub("", text).strip()


def _should_merge(
    prev_unit: Unit,
    prev_end_ms: int,
    curr_unit: Unit,
    curr_start_ms: int,
    max_gap_ms: int,
) -> bool:
    if prev_unit.style != curr_unit.style:
        return False
    gap = curr_start_ms - prev_end_ms
    if gap > max_gap_ms or gap < -500:
        return False

    prev_clean = _clean(prev_unit.text)
    curr_clean = _clean(curr_unit.text)
    if not prev_clean or not curr_clean:
        return False

    # Condição 1: fala anterior termina com continuidade explícita (... , - --) ou sem pontuação final
    ends_open = (
        prev_clean.endswith(("...", "…", ",", "-", "--"))
        or not prev_clean.endswith(_TERMINAL_PUNCT)
    )

    # Condição 2: fala atual começa com minúscula ou reticências
    starts_continuation = (
        curr_clean.startswith(("...", "…"))
        or (len(curr_clean) > 0 and curr_clean[0].islower())
    )

    return ends_open or starts_continuation


def merge_dialogue_units(
    doc: NormalizedDoc,
    classes: Mapping[str, UnitClass],
    tm_resolved_ids: set[str],
    max_gap_ms: int = 1500,
) -> MergedUnitsDoc:
    events_map = {ev.index: ev for ev in doc.events}
    units_map = {u.id: u for u in doc.units}

    # Filtra apenas unidades do tipo dialogue
    dialogue_units: list[tuple[Unit, int, int]] = []
    shortest_ms: dict[str, int] = {}  # menor ocorrência: o orçamento de caracteres tem de caber na mais curta
    for u in doc.units:
        ucls = classes.get(u.id)
        if not ucls or ucls.type != "dialogue":
            continue
        evs = [events_map[idx] for idx in u.events if idx in events_map]
        if not evs:
            continue
        start_ms = min(ev.start_ms for ev in evs)
        end_ms = max(ev.end_ms for ev in evs)
        shortest_ms[u.id] = min(max(0, ev.end_ms - ev.start_ms) for ev in evs)
        dialogue_units.append((u, start_ms, end_ms))

    # Ordena cronologicamente
    dialogue_units.sort(key=lambda item: (item[1], item[2], item[0].id))

    composite_list: list[CompositeUnit] = []
    current_group: list[tuple[Unit, int, int]] = []
    merged_count = 0

    def flush_group() -> None:
        nonlocal merged_count
        if not current_group:
            return
        if len(current_group) == 1:
            u = current_group[0][0]
            composite_list.append(
                CompositeUnit(
                    composite_id=u.id,
                    unit_ids=[u.id],
                    durations_ms=[shortest_ms[u.id]],
                    clean_text=_clean(u.text),
                    text_with_markers=u.text,
                )
            )
        else:
            comp_id = "+".join(u.id for u, _, _ in current_group)
            u_ids = [u.id for u, _, _ in current_group]
            durs = [shortest_ms[u.id] for u, _, _ in current_group]
            clean_parts = [_clean(u.text) for u, _, _ in current_group]
            marker_parts = [u.text for u, _, _ in current_group]
            composite_list.append(
                CompositeUnit(
                    composite_id=comp_id,
                    unit_ids=u_ids,
                    durations_ms=durs,
                    clean_text=" ".join(clean_parts),
                    text_with_markers=" ".join(marker_parts),
                )
            )
            merged_count += len(current_group) - 1
        current_group.clear()

    for unit, start_ms, end_ms in dialogue_units:
        # Se resolvida pela TM, não pode ser unida
        if unit.id in tm_resolved_ids:
            flush_group()
            current_group.append((unit, start_ms, end_ms))
            flush_group()
            continue

        if not current_group:
            current_group.append((unit, start_ms, end_ms))
            continue

        prev_unit, prev_s, prev_e = current_group[-1]
        if _should_merge(prev_unit, prev_e, unit, start_ms, max_gap_ms):
            current_group.append((unit, start_ms, end_ms))
        else:
            flush_group()
            current_group.append((unit, start_ms, end_ms))

    flush_group()
    return MergedUnitsDoc(units=composite_list, merged_count=merged_count)
