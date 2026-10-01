from translaterany.subtitles.classify import UnitClass
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc, merge_dialogue_units
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit


def test_merge_dialogue_units_with_ellipsis():
    ev1 = EventInfo(
        index=0,
        line_no=1,
        kind="dialogue",
        style="Default",
        start_ms=1000,
        end_ms=2000,
        layer=0,
        name="",
        prefix="",
        text="Even if you say that...",
        markers=["⟦1⟧"],
        suffix="",
        drawing=False,
        unit="u1",
    )
    u1 = Unit(id="u1", style="Default", text="Even if you say that...", markers=1, events=[0])

    ev2 = EventInfo(
        index=1,
        line_no=2,
        kind="dialogue",
        style="Default",
        start_ms=2200,
        end_ms=3500,
        layer=0,
        name="",
        prefix="",
        text="...I can't believe it.",
        markers=["⟦1⟧"],
        suffix="",
        drawing=False,
        unit="u2",
    )
    u2 = Unit(id="u2", style="Default", text="...I can't believe it.", markers=1, events=[1])

    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[ev1, ev2], units=[u1, u2])
    classes = {
        "u1": UnitClass(type="dialogue", uncertain=False, rule=""),
        "u2": UnitClass(type="dialogue", uncertain=False, rule=""),
    }

    merged = merge_dialogue_units(doc, classes, tm_resolved_ids=set(), max_gap_ms=1500)
    assert len(merged.units) == 1
    comp = merged.units[0]
    assert comp.composite_id == "u1+u2"
    assert comp.unit_ids == ["u1", "u2"]
    assert comp.durations_ms == [1000, 1300]
    assert "Even if you say that..." in comp.clean_text
    assert "I can't believe it." in comp.clean_text


def test_merge_dialogue_skips_tm_resolved():
    ev1 = EventInfo(
        index=0,
        line_no=1,
        kind="dialogue",
        style="Default",
        start_ms=1000,
        end_ms=2000,
        layer=0,
        name="",
        prefix="",
        text="Wait...",
        markers=["⟦1⟧"],
        suffix="",
        drawing=False,
        unit="u1",
    )
    u1 = Unit(id="u1", style="Default", text="Wait...", markers=1, events=[0])

    ev2 = EventInfo(
        index=1,
        line_no=2,
        kind="dialogue",
        style="Default",
        start_ms=2200,
        end_ms=3500,
        layer=0,
        name="",
        prefix="",
        text="for me.",
        markers=["⟦1⟧"],
        suffix="",
        drawing=False,
        unit="u2",
    )
    u2 = Unit(id="u2", style="Default", text="for me.", markers=1, events=[1])

    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[ev1, ev2], units=[u1, u2])
    classes = {
        "u1": UnitClass(type="dialogue", uncertain=False, rule=""),
        "u2": UnitClass(type="dialogue", uncertain=False, rule=""),
    }

    merged = merge_dialogue_units(doc, classes, tm_resolved_ids={"u1"}, max_gap_ms=1500)
    assert len(merged.units) == 2


def _event(index: int, start_ms: int, end_ms: int, text: str, unit: str) -> EventInfo:
    return EventInfo(
        index=index,
        line_no=index + 1,
        kind="dialogue",
        style="Default",
        start_ms=start_ms,
        end_ms=end_ms,
        layer=0,
        name="",
        prefix="",
        text=text,
        markers=[],
        suffix="",
        drawing=False,
        unit=unit,
    )


def test_merge_duration_of_repeated_text_is_shortest_occurrence():
    """Fala repetida ao longo do episódio é uma só unidade: a duração não pode ser o intervalo entre as
    ocorrências (minutos), senão o orçamento de caracteres deixa de limitar a tradução."""
    events = [_event(0, 10_000, 10_900, "Safe!", "u1"), _event(1, 500_000, 500_700, "Safe!", "u1")]
    unit = Unit(id="u1", style="Default", text="Safe!", markers=0, events=[0, 1])
    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=events, units=[unit])
    classes = {"u1": UnitClass(type="dialogue", uncertain=False, rule="")}

    merged = merge_dialogue_units(doc, classes, tm_resolved_ids=set())

    assert merged.units[0].durations_ms == [700]
