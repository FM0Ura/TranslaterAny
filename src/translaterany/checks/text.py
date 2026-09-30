"""Texto visível de uma linha: sem marcadores, sem tags, com quebras \\N como separador."""

import re

from translaterany.subtitles.segments import MARKER_RE

_TAGS = re.compile(r"\{[^}]*\}")
_BREAK = re.compile(r"\\[Nn]")
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def visible(text: str) -> str:
    text = MARKER_RE.sub("", text)
    text = _TAGS.sub("", text)
    return text.replace("\\h", " ").replace("'", "'")


def visible_lines(text: str) -> list[str]:
    return [part.strip() for part in _BREAK.split(visible(text))]


def plain(text: str) -> str:
    return " ".join(part for part in visible_lines(text) if part)


def words(text: str) -> list[str]:
    return _WORD.findall(plain(text).lower())
