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
