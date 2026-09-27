"""Análise contextual de cena para inferência de falantes, ouvintes, tom e desafios."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from translaterany.memory.models import CharacterEntry
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import MergedUnitsDoc

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
) -> SceneAnalysisDoc:
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

    lines_payload = [
        {"id": u.composite_id, "speaker": u.speaker, "text": u.clean_text}
        for u in merged_doc.units
    ]

    prompt = (
        f"Synopsis: {synopsis}\n"
        f"Known characters:\n{json.dumps(char_list, ensure_ascii=False)}\n\n"
        "Analyze the following dialogue lines. For each line, determine:\n"
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
            resp = client.generate(req)
            parsed = resp.output
        elif hasattr(client, "complete"):
            raw = client.complete(prompt)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = SceneAnalysisDoc.model_validate(json.loads(m.group(0))) if m else SceneAnalysisDoc()
        elif callable(client):
            raw = client(prompt)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = SceneAnalysisDoc.model_validate(json.loads(m.group(0))) if m else SceneAnalysisDoc()
        else:
            return SceneAnalysisDoc(lines=fallback_lines)

        final_lines = dict(fallback_lines)
        for k, v in parsed.lines.items():
            if k in final_lines:
                final_lines[k] = v
        return SceneAnalysisDoc(lines=final_lines)
    except Exception as exc:
        logger.warning("Falha na análise de cena por IA: %s. Adotando fallback de baixa confiança.", exc)
        return SceneAnalysisDoc(lines=fallback_lines)
