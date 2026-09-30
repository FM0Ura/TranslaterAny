"""Instantâneos de texto: linhas, estado acumulado, delta e resumos (M5)."""

import pytest

from translaterany.checks import Finding, LineInput
from translaterany.checks.metrics import HISTOGRAM_BINS, EpisodeMetrics, FinalMetrics
from translaterany.checks.snapshots import (
    advance_state,
    build_sources,
    composite_members,
    compute_delta,
    finding_keys,
    flagged,
    histogram_percentile,
    lines_for,
    reading_speed_stats,
    summarize,
)
from translaterany.config.model import ChecksConfig
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit


def ev(i: int, unit: str, start: int, end: int, style: str = "Default") -> EventInfo:
    return EventInfo(
        index=i, line_no=i, kind="dialogue", style=style, start_ms=start, end_ms=end, layer=0, name="",
        prefix="", text="t", markers=[], suffix="", drawing=False, unit=unit,
    )  # fmt: skip


DOC = NormalizedDoc(
    encoding=Encoding(bom=False, newline="\n"),
    format=[],
    events=[
        ev(0, "u1", 0, 2000),
        ev(1, "u2", 2100, 3000),
        ev(2, "u3", 5000, 6000, "Sign"),
        ev(3, "u3", 7000, 7500, "Sign"),
    ],
    units=[
        Unit(id="u1", style="Default", text="Wait for me...", markers=0, events=[0]),
        Unit(id="u2", style="Default", text="...I am coming!", markers=0, events=[1]),
        Unit(id="u3", style="Sign", text="Student Council", markers=0, events=[2, 3]),
    ],
)
CLASSES = Classification(
    main_style="Default",
    units={
        "u1": UnitClass(type="dialogue", uncertain=False, rule="r"),
        "u2": UnitClass(type="dialogue", uncertain=False, rule="r"),
        "u3": UnitClass(type="sign", uncertain=False, rule="r"),
    },
    counts={}, scenes=[],
)  # fmt: skip
MERGED = MergedUnitsDoc(
    units=[
        CompositeUnit(composite_id="u1+u2", unit_ids=["u1", "u2"], durations_ms=[2000, 900],
                      clean_text="Wait for me... I am coming!", text_with_markers="Wait for me... I am coming!"),
    ],
    merged_count=1,
)  # fmt: skip


def test_build_sources_units_and_composites() -> None:
    sources = build_sources(DOC, CLASSES, MERGED)
    assert sources["u3"].duration_ms == 500  # menor duração entre os eventos
    assert sources["u3"].line_type == "sign"
    assert sources["u1+u2"].duration_ms == 2900
    assert sources["u1+u2"].source == "Wait for me... I am coming!"
    assert sources["u1+u2"].line_type == "dialogue"
    assert composite_members(MERGED) == {"u1+u2": ["u1", "u2"]}
    assert composite_members(None) == {}


def test_lines_for_skips_unknown_keys() -> None:
    lines, unknown = lines_for({"u3": "Conselho", "zz": "?"}, build_sources(DOC, CLASSES, None))
    assert [ln.id for ln in lines] == ["u3"] and unknown == ["zz"]


def test_advance_state_replaces_composite_with_units() -> None:
    comps = composite_members(MERGED)
    state = advance_state({}, {"u1+u2": "Espere... estou indo!"}, comps)
    assert state == {"u1+u2": "Espere... estou indo!"}
    state = advance_state(state, {"u3": "Conselho"}, comps)
    assert set(state) == {"u1+u2", "u3"}
    state = advance_state(state, {"u1": "Espere...", "u2": "...estou indo!", "u3": "Conselho"}, comps)
    assert set(state) == {"u1", "u2", "u3"}


def test_compute_delta() -> None:
    prev = {"a": "abc", "b": "same"}
    new = {"a": "abd", "b": "same", "c": "novo"}
    delta = compute_delta(prev, new, {("x", "a"), ("y", "b")}, {("x", "a"), ("z", "c")})
    assert delta.changed == 2  # a mudou, c entrou
    assert delta.edit_ratio == pytest.approx((1 - 2 / 3 + 0) / 2, abs=1e-4)  # a: ratio 2/3; b: 0 (arredondado)
    assert (delta.new, delta.resolved) == (1, 1)
    assert compute_delta({}, {"a": "x"}, set(), set()).edit_ratio == 0.0


def test_summaries() -> None:
    findings = [
        Finding(check="negation", unit_id="u1", severity="warn", message="m"),
        Finding(check="reading_speed", unit_id="u1", severity="error", message="CPS"),
        Finding(check="reading_speed", unit_id="u1", severity="error", message="CPL"),
        Finding(check="reading_speed", unit_id="u2", severity="error", message="CPS"),
    ]
    summary = summarize(findings)
    assert summary["reading_speed"].error == 3 and summary["negation"].warn == 1
    assert flagged(findings).error == 2 and flagged(findings).warn == 1
    assert finding_keys(findings) == {("negation", "u1"), ("reading_speed", "u1"), ("reading_speed", "u2")}


def test_reading_speed_stats_and_percentile() -> None:
    lines = [
        LineInput(id=f"u{i}", line_type="dialogue", source="x", target="a" * cps, duration_ms=1000)
        for i, cps in enumerate([5, 10, 15, 20, 45])
    ]
    lines.append(LineInput(id="z", line_type="dialogue", source="x", target="aaa", duration_ms=0))
    lines.append(LineInput(id="s", line_type="sign", source="x", target="a" * 99, duration_ms=1000))
    stats = reading_speed_stats(lines, ChecksConfig())
    assert stats.cps_max == 45.0 and stats.over_limit == 2
    assert stats.cps_p50 == 15.0
    assert len(stats.cps_histogram) == HISTOGRAM_BINS and sum(stats.cps_histogram) == 5
    assert stats.cps_histogram[40] == 1  # 45 CPS cai na última faixa
    assert histogram_percentile(stats.cps_histogram, 0.5) == 16.0  # limite superior da faixa [15,16)
    assert histogram_percentile([0] * HISTOGRAM_BINS, 0.5) == 0.0


def test_metrics_model_roundtrip_uses_schema_alias() -> None:
    m = EpisodeMetrics(final=FinalMetrics())
    raw = m.model_dump_json(by_alias=True)
    assert '"schema":1' in raw.replace(" ", "")
    assert EpisodeMetrics.model_validate_json(raw) == m


def test_composite_flag_propagates() -> None:
    sources = build_sources(DOC, CLASSES, MERGED)
    assert sources["u1+u2"].composite and not sources["u3"].composite
    lines, _ = lines_for({"u1+u2": "x", "u3": "y"}, sources)
    assert {ln.id: ln.composite for ln in lines} == {"u1+u2": True, "u3": False}
