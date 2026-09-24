"""Documento normalizado: eventos segmentados e unidades de texto único."""

import re
from typing import Literal

from pydantic import BaseModel

from translaterany.subtitles.ass import AssDocument
from translaterany.subtitles.segments import fill, segment

_SPACES = re.compile(r"\s+")


class NormalizeError(Exception):
    """Invariante de segmentação violado (bug do parser): nada é gravado."""


class EventInfo(BaseModel):
    index: int
    line_no: int
    kind: Literal["dialogue", "comment"]
    style: str
    start_ms: int
    end_ms: int
    layer: int
    name: str
    prefix: str
    text: str
    markers: list[str]
    suffix: str
    drawing: bool
    unit: str | None  # None: comentário, vazio ou só desenho (nunca traduzido)


class Unit(BaseModel):
    id: str
    style: str
    text: str  # texto da 1ª ocorrência, com marcadores
    markers: int
    events: list[int]


class Encoding(BaseModel):
    bom: bool
    newline: str


class NormalizedDoc(BaseModel):
    encoding: Encoding
    format: list[str]
    events: list[EventInfo]
    units: list[Unit]


def normalize(doc: AssDocument) -> NormalizedDoc:
    events: list[EventInfo] = []
    units: dict[tuple[str, str, int], Unit] = {}
    for ev in doc.events:
        seg = segment(ev.text)
        if seg.prefix + fill(seg.text, seg.markers) + seg.suffix != ev.text:
            raise NormalizeError(f"segmentação não reconstrói o evento {ev.index} (linha {ev.line_no + 1})")
        style = ev.field("Style")
        unit_id = None
        clean = _SPACES.sub(" ", seg.text).strip()
        if ev.kind == "dialogue" and clean:
            key = (style, clean, len(seg.markers))
            if key not in units:
                units[key] = Unit(
                    id=f"u{len(units) + 1}", style=style, text=seg.text, markers=len(seg.markers), events=[]
                )
            units[key].events.append(ev.index)
            unit_id = units[key].id
        layer = ev.field("Layer")
        events.append(
            EventInfo(
                index=ev.index,
                line_no=ev.line_no,
                kind=ev.kind,
                style=style,
                start_ms=ev.start_ms,
                end_ms=ev.end_ms,
                layer=int(layer) if layer.lstrip("-").isdigit() else 0,
                name=ev.field("Name") or ev.field("Actor"),
                prefix=seg.prefix,
                text=seg.text,
                markers=list(seg.markers),
                suffix=seg.suffix,
                drawing=seg.drawing,
                unit=unit_id,
            )
        )
    return NormalizedDoc(
        encoding=Encoding(bom=doc.bom, newline=doc.newline),
        format=doc.format,
        events=events,
        units=list(units.values()),
    )
