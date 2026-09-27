from translaterany.llm.fake import FakeLLM
from translaterany.subtitles.classify import UnitClass
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit


def _make_doc():
    ev1 = EventInfo(
        index=0,
        line_no=1,
        kind="dialogue",
        style="Default",
        start_ms=0,
        end_ms=2000,
        layer=0,
        name="",
        prefix="",
        text="Normal dialogue",
        markers=["⟦1⟧"],
        suffix="",
        drawing=False,
        unit="u1",
    )
    u1 = Unit(id="u1", style="Default", text="Normal dialogue", markers=1, events=[0])

    ev2 = EventInfo(
        index=1,
        line_no=2,
        kind="dialogue",
        style="CustomStyle",
        start_ms=2000,
        end_ms=4000,
        layer=0,
        name="",
        prefix=r"{\pos(100,200)}",
        text="Chapter 1: The Beginning",
        markers=["⟦1⟧"],
        suffix="",
        drawing=False,
        unit="u2",
    )
    u2 = Unit(id="u2", style="CustomStyle", text="Chapter 1: The Beginning", markers=1, events=[1])

    return NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[ev1, ev2], units=[u1, u2])


def test_classify_stage_disambiguates_with_ai():
    doc = _make_doc()

    from translaterany.subtitles.classify import (
        DisambiguatedUnit,
        DisambiguateOutput,
        classify,
        disambiguate_uncertain_units,
    )

    fake_llm = FakeLLM(
        [
            DisambiguateOutput(
                units=[DisambiguatedUnit(id="u2", line_type="sign", reason="chapter title screen")]
            )
        ]
    )

    initial_cls = classify(doc, overrides={})
    assert initial_cls.units["u2"].uncertain is True

    updated_cls = disambiguate_uncertain_units(doc, initial_cls, fake_llm)
    assert updated_cls.units["u2"].uncertain is False
    assert updated_cls.units["u2"].type == "sign"
    assert updated_cls.units["u2"].rule == "ai_disambiguate"


def test_disambiguate_fallback_on_error():
    doc = _make_doc()

    fake_llm = FakeLLM(responses=["INVALID JSON {"])
    from translaterany.subtitles.classify import classify, disambiguate_uncertain_units
    initial_cls = classify(doc, overrides={})
    assert initial_cls.units["u2"].uncertain is True

    updated_cls = disambiguate_uncertain_units(doc, initial_cls, fake_llm)
    # Mantém classificação determinística com uncertain=True
    assert updated_cls.units["u2"].uncertain is True
