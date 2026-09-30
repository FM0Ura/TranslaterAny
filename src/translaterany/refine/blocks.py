"""Blocos de revisão por cena: alvos editáveis + contexto só de leitura da mesma cena."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from translaterany.subtitles.linebreak import flatten_breaks
from translaterany.subtitles.scenes import group_by_scene


@dataclass
class ReviewLine:
    id: str
    source: str
    target: str
    speaker: str
    tone: str
    budget: int | None
    signals: list[str]
    editable: bool


def build_blocks(ids: Sequence[str], targets: set[str], scene_of: Mapping[str, int], max_lines: int) -> list[list[str]]:
    blocks: list[list[str]] = []
    for scene in group_by_scene(ids, scene_of, len(ids) or 1):
        current: list[str] = []
        count = 0
        for item in scene:
            if item in targets and count >= max(1, max_lines):
                blocks.append(current)
                current, count = [], 0
            current.append(item)
            count += item in targets
        if current:
            blocks.append(current)
    return [b for b in blocks if any(i in targets for i in b)]


def render_block_prompt(lines: Sequence[ReviewLine]) -> str:
    payload = [
        {
            "id": ln.id,
            "en": flatten_breaks(ln.source),
            "pt": flatten_breaks(ln.target),
            "falante": ln.speaker,
            "tom": ln.tone,
            "limite_caracteres": ln.budget,
            "sinais": ln.signals,
            "editavel": ln.editable,
        }
        for ln in lines
    ]
    return json.dumps(payload, ensure_ascii=False)
