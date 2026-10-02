"""Montagem das linhas de cada instantâneo de texto, estado acumulado, delta e resumos."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from translaterany.checks.metrics import HISTOGRAM_BINS, ReadingSpeedStats, SeverityCounts, SnapshotDelta
from translaterany.checks.models import Finding, LineInput
from translaterany.checks.rules_context import measure
from translaterany.config.model import ChecksConfig
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc


@dataclass(frozen=True)
class LineSource:
    source: str
    line_type: str
    style: str
    duration_ms: int
    composite: bool = False


def build_sources(doc: NormalizedDoc, classes: Classification, merged: MergedUnitsDoc | None) -> dict[str, LineSource]:
    durations: dict[str, int] = {}
    for event in doc.events:
        if event.unit is not None:
            span = event.end_ms - event.start_ms
            durations[event.unit] = min(span, durations.get(event.unit, span))
    sources: dict[str, LineSource] = {}
    for unit in doc.units:
        kind = classes.units[unit.id].type if unit.id in classes.units else "dialogue"
        sources[unit.id] = LineSource(unit.text, kind, unit.style, durations.get(unit.id, 0))
    for comp in merged.units if merged else []:
        if len(comp.unit_ids) > 1 and comp.unit_ids[0] in sources:
            first = sources[comp.unit_ids[0]]
            sources[comp.composite_id] = LineSource(
                comp.text_with_markers, first.line_type, first.style, sum(comp.durations_ms),
                composite=True,
            )
    return sources


def composite_members(merged: MergedUnitsDoc | None) -> dict[str, list[str]]:
    return {c.composite_id: list(c.unit_ids) for c in (merged.units if merged else []) if len(c.unit_ids) > 1}


def lines_for(texts: Mapping[str, str], sources: Mapping[str, LineSource]) -> tuple[list[LineInput], list[str]]:
    lines: list[LineInput] = []
    unknown: list[str] = []
    for key, target in texts.items():
        src = sources.get(key)
        if src is None:
            unknown.append(key)
            continue
        lines.append(
            LineInput(
                id=key, line_type=src.line_type, style=src.style, source=src.source, target=target,
                duration_ms=src.duration_ms, composite=src.composite,
            )  # fmt: skip
        )
    return lines, unknown


def advance_state(
    state: Mapping[str, str], texts: Mapping[str, str], composites: Mapping[str, list[str]]
) -> dict[str, str]:
    new = dict(state)
    new.update(texts)
    for composite_id, members in composites.items():
        if composite_id in new and any(m in texts for m in members):
            del new[composite_id]
    return new


def finding_keys(findings: Iterable[Finding]) -> set[tuple[str, str | None]]:
    return {(f.check, f.unit_id) for f in findings}


def compute_delta(
    prev: Mapping[str, str], new: Mapping[str, str], prev_keys: set, new_keys: set
) -> SnapshotDelta:
    changed = sum(1 for key, text in new.items() if prev.get(key) != text)
    common = [key for key in new if key in prev]
    ratios = [1 - SequenceMatcher(None, prev[k], new[k]).ratio() for k in common]
    return SnapshotDelta(
        changed=changed,
        edit_ratio=round(sum(ratios) / len(ratios), 4) if ratios else 0.0,
        new=len(new_keys - prev_keys),
        resolved=len(prev_keys - new_keys),
    )


def summarize(findings: Iterable[Finding]) -> dict[str, SeverityCounts]:
    summary: dict[str, SeverityCounts] = {}
    for f in findings:
        counts = summary.setdefault(f.check, SeverityCounts())
        sev = "warn" if f.severity == "warning" else f.severity
        setattr(counts, sev, getattr(counts, sev) + 1)
    return summary


def flagged(findings: Iterable[Finding]) -> SeverityCounts:
    units: dict[str, set[str | None]] = {"info": set(), "warn": set(), "error": set()}
    for f in findings:
        sev = "warn" if f.severity == "warning" else f.severity
        units[sev].add(f.unit_id)
    return SeverityCounts(**{sev: len(ids) for sev, ids in units.items()})


def _index(values: Sequence[float], p: float) -> float:
    return values[int(p * (len(values) - 1))] if values else 0.0


def reading_speed_stats(lines: Iterable[LineInput], limits: ChecksConfig) -> ReadingSpeedStats:
    values: list[float] = []
    for line in lines:
        if line.line_type != "dialogue":
            continue
        cps = measure(line.target, line.duration_ms).cps
        if cps is not None:
            values.append(cps)
    values.sort()
    hist = [0] * HISTOGRAM_BINS
    for v in values:
        hist[min(int(v), HISTOGRAM_BINS - 1)] += 1
    return ReadingSpeedStats(
        cps_p50=round(_index(values, 0.5), 2),
        cps_p95=round(_index(values, 0.95), 2),
        cps_max=round(values[-1], 2) if values else 0.0,
        over_limit=sum(1 for v in values if v > limits.max_cps),
        cps_histogram=hist,
    )


def histogram_percentile(hist: Sequence[int], p: float) -> float:
    """Limite superior da faixa que atinge o percentil p (a última faixa, aberta, vale seu limite inferior)."""
    total = sum(hist)
    if not total:
        return 0.0
    acc = 0
    for i, n in enumerate(hist):
        acc += n
        if acc >= p * total:
            return float(i + 1) if i < len(hist) - 1 else float(i)
    return float(len(hist) - 1)
