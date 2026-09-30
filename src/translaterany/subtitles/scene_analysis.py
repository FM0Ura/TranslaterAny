"""Análise contextual de cena para inferência de falantes, ouvintes, tom e desafios."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from translaterany.memory.models import CharacterEntry
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc

logger = logging.getLogger(__name__)


class LineContext(BaseModel):
    speaker: str = "Unknown"
    listener: str = "Unknown"
    confidence: Literal["high", "medium", "low"] = "low"
    tone: str = "neutral"
    relationship: str = ""
    challenges: list[str] = Field(default_factory=list)


class SceneAnalysisDoc(BaseModel):
    lines: dict[str, LineContext] = Field(default_factory=dict)


def analyze_scenes(
    merged_doc: MergedUnitsDoc,
    scenes: list[Scene],
    characters: list[CharacterEntry],
    synopsis: str = "",
    client: Any | None = None,
    model: str = "review",
    unit_events: Mapping[str, list[int]] | None = None,
    max_lines_per_call: int = 40,
) -> SceneAnalysisDoc:
    """Uma chamada por cena (cenas longas em blocos de `max_lines_per_call`). O episódio inteiro numa
    chamada só estoura o contexto de modelos locais; uma falha afeta só a própria cena."""
    fallback_lines: dict[str, LineContext] = {
        u.composite_id: LineContext(
            speaker=u.speaker or "Unknown",
            listener="Unknown",
            confidence="low",
            tone="neutral",
            challenges=[],
        )
        for u in merged_doc.units
    }

    if client is None or not merged_doc.units:
        return SceneAnalysisDoc(lines=fallback_lines)

    char_list = [
        {
            "name": c.name,
            "gender": str(c.gender),
            "role": str(c.role),
            "speech_style": c.speech_style,
        }
        for c in characters
    ]
    final_lines = dict(fallback_lines)
    for group in _scene_groups(merged_doc, scenes, unit_events or {}, max_lines_per_call):
        parsed = _analyze_group(group, char_list, synopsis, client, model)
        for k, v in parsed.lines.items():
            if k in final_lines and any(u.composite_id == k for u in group):
                final_lines[k] = v
    return SceneAnalysisDoc(lines=final_lines)


def _scene_groups(
    merged_doc: MergedUnitsDoc,
    scenes: list[Scene],
    unit_events: Mapping[str, list[int]],
    max_lines: int,
) -> list[list[CompositeUnit]]:
    """Agrupa as falas pela cena do 1º evento da 1ª unidade; falas sem cena formam um grupo à parte."""
    scene_of_event = {ev: i for i, sc in enumerate(scenes) for ev in sc.events}
    by_scene: dict[int, list[CompositeUnit]] = {}
    for unit in merged_doc.units:
        events = unit_events.get(unit.unit_ids[0], []) if unit.unit_ids else []
        index = scene_of_event.get(events[0], len(scenes)) if events else len(scenes)
        by_scene.setdefault(index, []).append(unit)
    step = max(1, max_lines)
    return [
        units[i : i + step] for _, units in sorted(by_scene.items()) for i in range(0, len(units), step)
    ]


def _analyze_group(
    group: list[CompositeUnit], char_list: list[dict[str, Any]], synopsis: str, client: Any, model: str
) -> SceneAnalysisDoc:
    lines_payload = [{"id": u.composite_id, "speaker": u.speaker, "text": u.clean_text} for u in group]

    prompt = (
        f"Synopsis: {synopsis}\n"
        f"Known characters:\n{json.dumps(char_list, ensure_ascii=False)}\n\n"
        "Analyze the following dialogue lines of one scene. For each line, determine:\n"
        "- speaker: character name\n"
        "- listener: intended listener/interlocutor\n"
        "- confidence: 'high' (known main/supporting character), 'medium', or 'low' (unknown/crowd)\n"
        "- tone: emotional tone of the speaker (e.g. sarcastic, serious, angry, joyful)\n"
        "- relationship: brief description of their relationship\n"
        "- challenges: list of linguistic challenges (e.g. puns, honorifics, cultural references)\n\n"
        f"Lines:\n{json.dumps(lines_payload, ensure_ascii=False)}"
    )

    instructions = (
        "You are an expert anime director and subtitle translator. "
        "Analyze dialogue scenes and output valid JSON matching the requested schema."
    )

    try:
        if hasattr(client, "generate"):
            from translaterany.llm.client import LLMRequest

            req = LLMRequest(
                model=model,
                instructions=instructions,
                prompt=prompt,
                output_type=SceneAnalysisDoc,
                tag="scene_analysis",
            )
            return client.generate(req).output
        if hasattr(client, "complete"):
            raw = client.complete(prompt)
        elif callable(client):
            raw = client(prompt)
        else:
            return SceneAnalysisDoc()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return SceneAnalysisDoc.model_validate(json.loads(m.group(0))) if m else SceneAnalysisDoc()
    except Exception as exc:
        first = group[0].composite_id if group else "?"
        logger.warning(
            "Falha na análise de cena por IA (bloco a partir de %s): %s. Adotando fallback de baixa confiança.",
            first,
            exc,
        )
        return SceneAnalysisDoc()
