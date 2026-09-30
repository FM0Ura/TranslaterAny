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


def _windowed(scene: Sequence[str], group: Sequence[str], targets: set[str], window: int) -> list[str]:
    """Alvos do grupo + até `window` falas de contexto (não alvos) antes e depois de cada um."""
    position = {item: n for n, item in enumerate(scene)}
    keep = {position[t] for t in group}
    for t in group:
        for step in (-1, 1):
            n, taken = position[t] + step, 0
            while 0 <= n < len(scene) and taken < window:
                if scene[n] in targets:
                    if scene[n] not in group:  # alvo de outro bloco: o contexto para aqui
                        break
                else:
                    keep.add(n)
                    taken += 1
                n += step
    return [scene[n] for n in sorted(keep)]


def build_blocks(
    ids: Sequence[str],
    targets: set[str],
    scene_of: Mapping[str, int],
    max_lines: int,
    context_window: int | None = None,
) -> list[list[str]]:
    blocks: list[list[str]] = []
    for scene in group_by_scene(ids, scene_of, len(ids) or 1):
        if context_window is not None:
            scene_targets = [i for i in scene if i in targets]
            size = max(1, max_lines)
            for start in range(0, len(scene_targets), size):
                blocks.append(_windowed(scene, scene_targets[start : start + size], targets, context_window))
            continue
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
