from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.normalize import normalize


def _doc(*events: str) -> bytes:
    head = (
        "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return (head + "".join(e + "\n" for e in events)).encode("utf-8")


def _ev(start: str, style: str, text: str, kind: str = "Dialogue", end: str | None = None) -> str:
    return f"{kind}: 0,0:00:{start},0:00:{end or start},{style},,0,0,0,,{text}"


def test_frame_by_frame_copies_share_one_unit() -> None:
    data = _doc(
        _ev("01.00", "Sign", "{\\pos(10,10)}Rua Principal"),
        _ev("01.04", "Sign", "{\\pos(11,10)}Rua Principal"),
        _ev("01.08", "Sign", "{\\pos(12,10)}Rua  Principal "),
    )
    nd = normalize(parse_ass(data))
    assert len(nd.units) == 1 and nd.units[0].events == [0, 1, 2]
    assert {e.unit for e in nd.events} == {"u1"}


def test_units_split_by_style_and_marker_count() -> None:
    nd = normalize(
        parse_ass(
            _doc(
                _ev("01.00", "Default", "Oi"),
                _ev("02.00", "Sign", "Oi"),
                _ev("03.00", "Default", "O{\\i1}i"),
            )
        )
    )
    assert [u.id for u in nd.units] == ["u1", "u2", "u3"]


def test_comments_empty_and_drawings_have_no_unit() -> None:
    nd = normalize(
        parse_ass(
            _doc(
                _ev("01.00", "Default", "nota", kind="Comment"),
                _ev("02.00", "Default", "{\\fad(1,1)}"),
                _ev("03.00", "Default", "{\\p1}m 0 0 l 1 1{\\p0}"),
                _ev("04.00", "Default", "Fala"),
            )
        )
    )
    assert [e.unit for e in nd.events] == [None, None, None, "u1"]
    assert nd.events[2].drawing
