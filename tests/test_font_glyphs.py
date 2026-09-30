# tests/test_font_glyphs.py
"""Checagem de glifos das fontes anexadas (M5). Fontes geradas no teste; nenhum binário no repositório."""

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from translaterany.checks.fonts import check_font_glyphs, event_fonts, load_font_faces, style_fonts
from translaterany.media.mkv import Attachment, MkvInfo, font_attachments
from translaterany.subtitles.normalize import EventInfo


def make_font(path: Path, family: str, chars: str) -> Path:
    names = [".notdef"] + [f"uni{ord(c):04X}" for c in chars]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 500))
        pen.lineTo((500, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (500, 0) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(str(path))
    return path


ASS = (
    b"[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
    b"Style: Default,Open Sans,48\nStyle: Vert,@Gothic,40\n\n[Events]\n"
    b"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def event(style: str, prefix: str = "", markers: list[str] | None = None) -> EventInfo:
    return EventInfo(
        index=0, line_no=0, kind="dialogue", style=style, start_ms=0, end_ms=1000, layer=0, name="",
        prefix=prefix, text="x", markers=markers or [], suffix="", drawing=False, unit="u1",
    )  # fmt: skip


def test_style_fonts_strip_vertical_prefix() -> None:
    assert style_fonts(ASS) == {"Default": "Open Sans", "Vert": "Gothic"}


def test_event_fonts_include_inline_fn() -> None:
    styles = style_fonts(ASS)
    assert event_fonts(event("Default"), styles) == {"open sans"}
    assert event_fonts(event("Default", prefix="{\\fnComic Neue\\b1}"), styles) == {"open sans", "comic neue"}
    assert event_fonts(event("Nope", markers=["{\\fn@Arial}"]), styles) == {"arial"}


def test_glyph_present_missing_and_not_attached(tmp_path: Path) -> None:
    font = make_font(tmp_path / "a.ttf", "Open Sans", "abcãç ")
    faces, problems = load_font_faces([font])
    assert problems == []
    assert "open sans" in faces
    found = check_font_glyphs({"open sans": set("abc"), "missing font": set("a")}, faces)
    assert [(f.severity, f.check) for f in found] == [("info", "font_glyphs")]  # só a não anexada
    found = check_font_glyphs({"open sans": set("abcé")}, faces)
    assert found[0].severity == "warn" and "é" in found[0].message


def test_unreadable_font_is_info(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"\x00\x01\x00\x00fake-font")
    faces, problems = load_font_faces([bad])
    assert faces == {}
    assert problems[0].severity == "info" and "bad.ttf" in problems[0].message


def test_font_attachments_by_mime_or_extension() -> None:
    info = MkvInfo(
        tracks=(),
        attachments=(
            Attachment(1, "a.ttf", "application/x-truetype-font"),
            Attachment(2, "b.OTF", "application/octet-stream"),
            Attachment(3, "cover.jpg", "image/jpeg"),
            Attachment(4, "c", "font/ttf"),
        ),
        duration_ns=None,
    )
    assert [a.id for a in font_attachments(info)] == [1, 2, 4]
