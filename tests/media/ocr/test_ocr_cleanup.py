"""Correção determinística de '|' no lugar de 'I' no texto OCR (dados sintéticos)."""

import pytest

from translaterany.media.ocr.cleanup import fix_pipe_as_capital_i
from translaterany.media.ocr.engine import _parse_hocr


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("| could say the same.", "I could say the same."),
        ("What will | see at the end?", "What will I see at the end?"),
        ("| know | don't look it,", "I know I don't look it,"),
        ("| need to wake up.\\N| have to go.", "I need to wake up.\\NI have to go."),
        ("Acrinol\\N| can't even connect", "Acrinol\\NI can't even connect"),
        ("{\\i1}| could say{\\i0}", "{\\i1}I could say{\\i0}"),
        ("{\\i1}Hello{\\i0}\\N{\\i1}| agree{\\i0}", "{\\i1}Hello{\\i0}\\N{\\i1}I agree{\\i0}"),
        ("|'m fine, |'ll go, |'ve done it, |'d say so.", "I'm fine, I'll go, I've done it, I'd say so."),
        ("|’m fine", "I’m fine"),
        ("Am | right? Yes, | do.", "Am I right? Yes, I do."),
        ("- | know.", "- I know."),
        ("(| think)", "(I think)"),
    ],
)
def test_isolated_pipe_becomes_capital_i(raw: str, expected: str) -> None:
    assert fix_pipe_as_capital_i(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "P|..Please do that.",
        "a|b and c||d",
        "see http://example.com/a|b now",
        "{\\k20}ka{\\k30}|ra",
        "{\\fn|x}Text",
        "|",
        "{\\i1}|{\\i0}",
        "Plain text without any bars.",
        "",
    ],
)
def test_pipe_inside_words_urls_tags_or_alone_is_untouched(text: str) -> None:
    assert fix_pipe_as_capital_i(text) == text


def test_parse_hocr_applies_fix_and_keeps_italic_markup() -> None:
    hocr = "<span class='ocr_line'><em>| could say</em> the same</span><span class='ocr_line'>What will | see</span>"
    assert _parse_hocr(hocr) == "{\\i1}I could say{\\i0} the same\\NWhat will I see"


def test_parse_hocr_leaves_pipes_alone_for_non_english() -> None:
    assert _parse_hocr("<span>a | b</span>", lang="jpn") == "a | b"
