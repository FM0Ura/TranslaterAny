"""Fontes do .ass: família por estilo, trocas \\fn e glifos disponíveis (fontTools). Só avisa, nunca bloqueia."""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from translaterany.checks.models import Finding
from translaterany.subtitles.ass import split_lines
from translaterany.subtitles.normalize import EventInfo

_FN = re.compile(r"\\fn([^\\}]+)")
_NAME_IDS = (1, 4, 16)  # família, nome completo, família tipográfica


def _norm(name: str) -> str:
    return name.strip().lstrip("@").strip().lower()


def style_fonts(ass_data: bytes) -> dict[str, str]:
    """Estilo -> família da fonte, lidos da seção [V4+ Styles]/[V4 Styles]."""
    text = ass_data.decode("utf-8-sig", errors="replace")
    fonts: dict[str, str] = {}
    in_styles = False
    fmt: list[str] = []
    for raw in split_lines(text):
        line = raw.strip()
        if line.startswith("["):
            in_styles = line.lower() in ("[v4+ styles]", "[v4 styles]")
            continue
        if not in_styles or ":" not in line:
            continue
        key, _, value = line.partition(":")
        parts = [p.strip() for p in value.split(",")]
        if key.strip().lower() == "format":
            fmt = [p.lower() for p in parts]
        elif key.strip().lower() == "style" and "name" in fmt and "fontname" in fmt:
            if len(parts) < len(fmt):
                continue  # linha de estilo malformada: ignora
            fonts[parts[fmt.index("name")]] = parts[fmt.index("fontname")].lstrip("@")
    return fonts


def event_fonts(event: EventInfo, styles: Mapping[str, str]) -> set[str]:
    names = {_norm(styles[event.style])} if event.style in styles else set()
    for block in (event.prefix, *event.markers):
        names.update(_norm(m) for m in _FN.findall(block))
    return {n for n in names if n}


def load_font_faces(paths: Iterable[Path]) -> tuple[dict[str, frozenset[int]], list[Finding]]:
    faces: dict[str, frozenset[int]] = {}
    problems: list[Finding] = []
    for path in paths:
        try:
            fonts = TTCollection(str(path)).fonts if path.suffix.lower() == ".ttc" else [TTFont(str(path), lazy=True)]
            for font in fonts:
                cmap = frozenset((font.getBestCmap() or {}).keys())
                for record in font["name"].names:
                    if record.nameID in _NAME_IDS:
                        faces[_norm(record.toUnicode())] = cmap
        except Exception as exc:  # fonte corrompida/estranha: só informa
            problems.append(
                Finding(
                    check="font_glyphs", severity="info", message=f"fonte ilegível '{path.name}': {type(exc).__name__}"
                )
            )
    return faces, problems


def check_font_glyphs(chars_by_font: Mapping[str, set[str]], faces: Mapping[str, frozenset[int]]) -> list[Finding]:
    findings: list[Finding] = []
    for name in sorted(chars_by_font):
        chars = {c for c in chars_by_font[name] if not c.isspace()}
        cmap = faces.get(name)
        if cmap is None:
            findings.append(
                Finding(check="font_glyphs", severity="info", message=f"fonte '{name}' não está anexada ao MKV")
            )
            continue
        missing = sorted(c for c in chars if ord(c) not in cmap)
        if missing:
            findings.append(
                Finding(
                    check="font_glyphs",
                    severity="warn",
                    message=f"fonte '{name}' sem glifos: {', '.join(missing[:10])}",
                    value=float(len(missing)),
                )
            )
    return findings
