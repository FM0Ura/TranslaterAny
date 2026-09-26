"""Parser e gravação de .ass orientados a linhas: tudo que não é texto de evento sai byte a byte."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

BOM = "﻿"
MARKER = "; TranslaterAny"
_EVENT_KINDS = {"dialogue": "dialogue", "comment": "comment"}
_LINE_BREAK = re.compile(r"(?<=\n)|(?<=\r)(?!\n)")


class AssError(Exception):
    """Arquivo .ass malformado. Mensagem pronta para o usuário."""


@dataclass(frozen=True)
class AssEvent:
    index: int  # ordem entre os eventos
    line_no: int  # linha no arquivo (0-based)
    kind: Literal["dialogue", "comment"]
    fields: dict[str, str]  # colunas do Format, exceto Text
    text: str
    text_offset: int  # posição, na linha, onde começa o campo de texto

    def field(self, name: str) -> str:
        """Valor de uma coluna sem diferenciar maiúsculas (ex.: 'style')."""
        for key, value in self.fields.items():
            if key.lower() == name.lower():
                return value
        return ""

    @property
    def start_ms(self) -> int:
        return ass_time_to_ms(self.field("Start"))

    @property
    def end_ms(self) -> int:
        return ass_time_to_ms(self.field("End"))


@dataclass
class AssDocument:
    lines: list[str]  # linhas decodificadas, com terminadores
    bom: bool
    newline: str
    format: list[str]
    events: list[AssEvent] = field(default_factory=list)


def split_lines(text: str) -> list[str]:
    """Quebra só em \\r\\n, \\n e \\r, mantendo os terminadores. `str.splitlines` também quebraria em
    U+2028, \\x0c etc., que podem aparecer dentro do texto de um evento."""
    return [line for line in _LINE_BREAK.split(text) if line]


def ass_time_to_ms(value: str) -> int:
    """'H:MM:SS.cc' -> milissegundos."""
    try:
        hours, minutes, seconds = value.strip().split(":")
        return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    except ValueError as exc:
        raise AssError(f"tempo inválido: {value!r}") from exc


def parse_ass(data: bytes) -> AssDocument:
    bom = data.startswith(BOM.encode("utf-8"))
    try:
        text = data.decode("utf-8-sig" if bom else "utf-8")
    except UnicodeDecodeError as exc:
        raise AssError("ASS malformado: não é UTF-8") from exc
    lines = split_lines(text)
    newline = "\r\n" if sum(line.endswith("\r\n") for line in lines) * 2 > len(lines) else "\n"
    doc = AssDocument(lines=lines, bom=bom, newline=newline, format=[])

    section = ""
    seen_events = False
    for line_no, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            seen_events = seen_events or section == "events"
            continue
        if section != "events" or ":" not in stripped:
            continue
        label, _, value = line.partition(":")
        label = label.strip().lower()
        if label == "format":
            doc.format = [col.strip() for col in value.split(",")]
            if not doc.format or doc.format[-1].lower() != "text":
                raise AssError(f"ASS malformado: a coluna Text precisa ser a última do Format (linha {line_no + 1})")
            continue
        if label not in _EVENT_KINDS:
            continue
        if not doc.format:
            raise AssError(f"ASS malformado: evento antes da linha Format (linha {line_no + 1})")
        doc.events.append(_parse_event(line, line_no, _EVENT_KINDS[label], doc.format, len(doc.events)))

    if not seen_events:
        raise AssError("ASS malformado: seção [Events] ausente")
    if not doc.format:
        raise AssError("ASS malformado: linha Format ausente em [Events]")
    return doc


def _parse_event(line: str, line_no: int, kind: str, fmt: list[str], index: int) -> AssEvent:
    body = line.rstrip("\r\n")
    head_end = body.index(":") + 1
    offset = head_end
    values: list[str] = []
    for _ in range(len(fmt) - 1):
        comma = body.find(",", offset)
        if comma < 0:
            raise AssError(f"ASS malformado: evento com campos a menos (linha {line_no + 1})")
        values.append(body[offset:comma].strip())
        offset = comma + 1
    fields = dict(zip(fmt[:-1], values, strict=True))
    return AssEvent(index=index, line_no=line_no, kind=kind, fields=fields, text=body[offset:], text_offset=offset)  # type: ignore[arg-type]


def render_ass(doc: AssDocument, new_texts: Mapping[int, str], *, marker: bool = False) -> bytes:
    """Troca só o campo de texto dos eventos indicados; `marker` insere a marca de autoria."""
    lines = list(doc.lines)
    for index, new_text in new_texts.items():
        event = doc.events[index]
        if new_text == event.text:
            continue
        original = lines[event.line_no]
        terminator = original[len(original.rstrip("\r\n")) :]
        lines[event.line_no] = original[: event.text_offset] + new_text + terminator
    if marker and not any(line.strip() == MARKER for line in lines):
        at = next((i + 1 for i, line in enumerate(lines) if line.strip().lower() == "[script info]"), 0)
        lines.insert(at, MARKER + doc.newline)
    return ((BOM if doc.bom else "") + "".join(lines)).encode("utf-8")


def has_marker(data: bytes) -> bool:
    """O .ass foi produzido pela app a partir de uma tradução (marca D10)?"""
    text = data.decode("utf-8", errors="replace")
    return any(line.strip() == MARKER for line in split_lines(text))
