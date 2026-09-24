import pytest

from translaterany.subtitles.segments import SegmentError, fill, marker_ids, segment


def _roundtrip(raw: str) -> None:
    seg = segment(raw)
    assert seg.prefix + fill(seg.text, seg.markers) + seg.suffix == raw


def test_prefix_inline_and_suffix() -> None:
    raw = "{\\an8\\pos(960,80)}Olá {\\i1}mundo{\\i0}!{\\fad(0,200)}"
    seg = segment(raw)
    assert seg.prefix == "{\\an8\\pos(960,80)}"
    assert seg.text == "Olá ⟦1⟧mundo⟦2⟧!"
    assert seg.markers == ("{\\i1}", "{\\i0}")
    assert seg.suffix == "{\\fad(0,200)}"
    assert not seg.drawing
    _roundtrip(raw)


def test_plain_text_and_line_breaks() -> None:
    seg = segment("Primeira linha\\NSegunda\\hlinha")
    assert seg.prefix == seg.suffix == "" and seg.markers == ()
    assert seg.text == "Primeira linha\\NSegunda\\hlinha"


def test_adjacent_tags_become_one_marker() -> None:
    seg = segment("a{\\i1}{\\b1}b")
    assert seg.markers == ("{\\i1}{\\b1}",) and seg.text == "a⟦1⟧b"


def test_drawing_only() -> None:
    raw = "{\\p1\\pos(10,10)}m 0 0 l 100 0 100 100 0 100{\\p0}"
    seg = segment(raw)
    assert seg.drawing and seg.text == "" and seg.prefix == raw
    _roundtrip(raw)


def test_pos_is_not_drawing() -> None:
    assert not segment("{\\pos(1,2)}Texto").drawing


def test_drawing_then_text() -> None:
    raw = "{\\p1}m 0 0 l 5 5{\\p0}Legenda"
    seg = segment(raw)
    assert seg.drawing and seg.text == "Legenda"
    _roundtrip(raw)


def test_karaoke_syllables_become_markers() -> None:
    raw = "{\\k20}ka{\\k30}ra{\\k25}o{\\k40}ke"
    seg = segment(raw)
    assert seg.prefix == "{\\k20}" and seg.text == "ka⟦1⟧ra⟦2⟧o⟦3⟧ke"
    _roundtrip(raw)


def test_only_tags() -> None:
    seg = segment("{\\fad(100,100)}")
    assert seg.text == "" and seg.prefix == "{\\fad(100,100)}"


def test_reserved_characters_are_rejected() -> None:
    with pytest.raises(SegmentError):
        segment("texto com ⟦1⟧ literal")


def test_marker_ids() -> None:
    assert marker_ids("a⟦1⟧b⟦2⟧c⟦1⟧") == [1, 2, 1]
