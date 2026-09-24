import pytest

from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.classify import classify, style_categories, style_tokens
from translaterany.subtitles.normalize import normalize


def _doc(*events: str) -> bytes:
    head = (
        "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return (head + "".join(e + "\n" for e in events)).encode("utf-8")


def _ev(start: str, style: str, text: str, kind: str = "Dialogue", end: str | None = None) -> str:
    return f"{kind}: 0,0:00:{start},0:00:{end or start},{style},,0,0,0,,{text}"


@pytest.mark.parametrize(
    ("style", "tokens"),
    [
        ("CharlotteEDEnglish", ["charlotte", "ed", "english"]),
        ("OP - Romaji 2", ["op", "romaji", "2"]),
        ("PikminimanSigns", ["pikminiman", "signs"]),
        ("Charlotte-IN01-Eng", ["charlotte", "in", "in01", "01", "eng"]),
    ],
)
def test_style_tokens(style: str, tokens: list[str]) -> None:
    assert style_tokens(style) == tokens


@pytest.mark.parametrize(
    ("style", "cats"),
    [
        ("CharlotteEDRomaji", {"romaji", "song"}),
        ("OP_Rom", {"romaji", "song"}),
        ("ED Ro Blue", {"romaji", "song"}),
        ("CharlotteEDEnglish", {"song"}),
        ("OP_Eng", {"song"}),
        ("Charlotte-IN01-Eng", {"song"}),
        ("Sign-1", {"sign"}),
        ("SIGNS =", {"sign"}),
        ("FyuSigns", {"sign"}),
        ("GJM_Main", set()),
        ("Tensai_Main", set()),
        ("Default", set()),
        ("Mirror", set()),
    ],
)
def test_style_categories(style: str, cats: set[str]) -> None:
    assert style_categories(style) == cats


def _classify(*events: str, overrides: dict[str, str] | None = None):
    nd = normalize(parse_ass(_doc(*events)))
    return nd, classify(nd, overrides or {})


def test_classification_rules() -> None:
    nd, c = _classify(
        _ev("01.00", "GJM_Main", "Fala um", end="02.00"),
        _ev("02.50", "GJM_Main", "Fala dois", end="03.00"),
        _ev("04.00", "CharlotteEDRomaji", "sora no kanata"),
        _ev("05.00", "CharlotteEDEnglish", "Beyond the sky"),
        _ev("06.00", "FyuSigns", "Estação"),
        _ev("07.00", "OP_Rom", "{\\k20}ka{\\k20}ze"),
        _ev("08.00", "Misc", "{\\pos(1,1)}Aviso"),
        _ev("09.00", "OP Sign", "Letreiro"),
    )
    types = {u.text: c.units[u.id] for u in nd.units}
    assert c.main_style == "GJM_Main"
    assert types["Fala um"].type == "dialogue" and not types["Fala um"].uncertain
    assert types["sora no kanata"].type == "romaji"
    assert types["Beyond the sky"].type == "song"
    assert types["Estação"].type == "sign"
    assert types["ka⟦1⟧ze"].type == "karaoke"
    assert types["Aviso"].type == "sign" and types["Aviso"].uncertain
    assert types["Letreiro"].type == "song" and types["Letreiro"].uncertain  # 'op' e 'sign' ao mesmo tempo
    assert c.counts == {"dialogue": 2, "karaoke": 1, "romaji": 1, "sign": 2, "song": 2}


def test_series_overrides_win() -> None:
    nd, c = _classify(_ev("01.00", "Mirror", "Reflexo"), overrides={"Mirror": "sign"})
    assert c.units["u1"].type == "sign" and c.units["u1"].rule == "series.toml"


def test_scenes_split_on_gaps() -> None:
    _, c = _classify(
        _ev("01.00", "Default", "a", end="02.00"),
        _ev("04.00", "Default", "b", end="05.00"),
        _ev("20.00", "Default", "c", end="21.00"),
        _ev("22.00", "Sign-1", "placa", end="23.00"),
    )
    assert [s.events for s in c.scenes] == [[0, 1], [2]]
    assert (c.scenes[0].start_ms, c.scenes[0].end_ms) == (1000, 5000)
