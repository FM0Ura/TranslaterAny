"""Separação do texto de um evento em prefixo de tags, texto com marcadores e sufixo de tags."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

_BLOCK = re.compile(r"(\{[^}]*\})")
_DRAWING = re.compile(r"\\p(\d+)")
MARKER_RE = re.compile(r"⟦(\d+)⟧")


class SegmentError(Exception):
    """O texto não pode ser segmentado sem ambiguidade."""


@dataclass(frozen=True)
class Segmented:
    prefix: str  # tags antes do primeiro texto
    text: str  # texto com marcadores ⟦n⟧ no lugar das tags internas
    markers: tuple[str, ...]  # tags internas, na ordem
    suffix: str  # tags depois do último texto
    drawing: bool  # continha desenho vetorial (\p1…)


def segment(raw: str) -> Segmented:
    if "⟦" in raw or "⟧" in raw:
        raise SegmentError("o texto original contém os caracteres reservados ⟦ ⟧")
    items: list[tuple[str, str]] = []  # ("tag" | "text", conteúdo)
    drawing_mode = False
    had_drawing = False
    for token in _BLOCK.split(raw):
        if not token:
            continue
        if token.startswith("{") and token.endswith("}"):
            for level in _DRAWING.findall(token):
                drawing_mode = int(level) > 0
            items.append(("tag", token))
        elif drawing_mode:
            had_drawing = True
            items.append(("tag", token))  # comandos vetoriais: nunca são texto
        else:
            items.append(("text", token))

    merged: list[tuple[str, str]] = []
    for kind, content in items:
        if merged and merged[-1][0] == kind:
            merged[-1] = (kind, merged[-1][1] + content)
        else:
            merged.append((kind, content))

    text_positions = [i for i, (kind, _) in enumerate(merged) if kind == "text"]
    if not text_positions:
        return Segmented(prefix=raw, text="", markers=(), suffix="", drawing=had_drawing)
    first, last = text_positions[0], text_positions[-1]
    prefix = "".join(content for _, content in merged[:first])
    suffix = "".join(content for _, content in merged[last + 1 :])
    markers: list[str] = []
    parts: list[str] = []
    for kind, content in merged[first : last + 1]:
        if kind == "text":
            parts.append(content)
        else:
            markers.append(content)
            parts.append(f"⟦{len(markers)}⟧")
    return Segmented(prefix=prefix, text="".join(parts), markers=tuple(markers), suffix=suffix, drawing=had_drawing)


def fill(text: str, markers: Sequence[str]) -> str:
    """Devolve as tags internas no lugar dos marcadores ⟦n⟧."""
    return MARKER_RE.sub(lambda m: markers[int(m.group(1)) - 1], text)


def marker_ids(text: str) -> list[int]:
    return [int(m) for m in MARKER_RE.findall(text)]
