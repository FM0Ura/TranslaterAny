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
from translaterany.subtitles.scenes import group_by_scene, scene_index_of

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
    by_id = {u.composite_id: u for u in merged_doc.units}
    members = {u.composite_id: list(u.unit_ids) for u in merged_doc.units}
    ids = [u.composite_id for u in merged_doc.units]
    scene_of = scene_index_of(ids, members, unit_events or {}, scenes)
    for id_group in group_by_scene(ids, scene_of, max_lines_per_call):
        group = [by_id[i] for i in id_group]
        parsed = _analyze_group(group, char_list, synopsis, client, model)
        for k, v in parsed.lines.items():
            if k in final_lines and k in id_group:
                final_lines[k] = v
    return SceneAnalysisDoc(lines=final_lines)


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
