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


_ROLE_PRIORITY: dict[str, int] = {
    "main": 3,
    "supporting": 2,
    "guest": 1,
    "unknown": 0,
}

_VOCATIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:(?:Hey|Listen|Look|Wait|Oh),?\s+)?([A-Za-z]+)[,!]\s+", re.IGNORECASE),
    re.compile(r"[,\-—]\s*([A-Za-z]+)[\.!?]+$", re.IGNORECASE),
    re.compile(r"^([A-Za-z]+)[!?]+$", re.IGNORECASE),
)


def _build_known_names(characters: list[CharacterEntry]) -> dict[str, str]:
    """Mapeia tokens de nomes e apelidos (minúsculos) para o nome canônico do personagem.
    Personagens principais (MAIN) têm precedência sobre coadjuvantes na resolução de nomes compartilhados.
    """
    sorted_chars = sorted(
        characters,
        key=lambda c: _ROLE_PRIORITY.get(str(c.role).lower(), 0),
        reverse=True,
    )
    known: dict[str, str] = {}
    for c in sorted_chars:
        candidates = [c.name] + c.name.split() + list(c.aliases)
        for a in c.aliases:
            candidates.extend(a.split())
        for token in candidates:
            cleaned = token.lower().strip()
            if len(cleaned) >= 3 and cleaned not in known:
                known[cleaned] = c.name
    return known


def _extract_vocative(text: str, known_names: dict[str, str]) -> str | None:
    """Detecta se uma frase interpela diretamente um personagem conhecido pelo nome/vocativo."""
    if not known_names or not text:
        return None
    cleaned = text.strip()
    for pattern in _VOCATIVE_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            token = match.group(1).lower()
            if token in known_names:
                return known_names[token]
    return None


def _apply_vocative_safeguard(
    parsed: SceneAnalysisDoc,
    group: list[CompositeUnit],
    known_names: dict[str, str],
) -> None:
    """Garante que falas contendo vocativos não atribuam o personagem chamado como orador (speaker),
    corrigindo inversões comuns entre orador e ouvinte.
    """
    if not known_names:
        return

    for unit in group:
        ctx = parsed.lines.get(unit.composite_id)
        if not ctx:
            continue
        addressed = _extract_vocative(unit.clean_text, known_names)
        if not addressed:
            continue

        if ctx.speaker == addressed:
            if ctx.listener != "Unknown" and ctx.listener != addressed:
                ctx.speaker, ctx.listener = ctx.listener, ctx.speaker
            else:
                ctx.speaker = "Unknown"
                ctx.listener = addressed
        elif ctx.listener == "Unknown":
            ctx.listener = addressed


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
            "aliases": c.aliases,
        }
        for c in characters
    ]
    known_names = _build_known_names(characters)
    final_lines = dict(fallback_lines)
    by_id = {u.composite_id: u for u in merged_doc.units}
    members = {u.composite_id: list(u.unit_ids) for u in merged_doc.units}
    ids = [u.composite_id for u in merged_doc.units]
    scene_of = scene_index_of(ids, members, unit_events or {}, scenes)
    for id_group in group_by_scene(ids, scene_of, max_lines_per_call):
        group = [by_id[i] for i in id_group]
        parsed = _analyze_group(group, char_list, synopsis, client, model, known_names)
        for k, v in parsed.lines.items():
            if k in final_lines and k in id_group:
                final_lines[k] = v
    return SceneAnalysisDoc(lines=final_lines)


def _analyze_group(
    group: list[CompositeUnit],
    char_list: list[dict[str, Any]],
    synopsis: str,
    client: Any,
    model: str,
    known_names: dict[str, str] | None = None,
) -> SceneAnalysisDoc:
    lines_payload = [
        {
            "id": u.composite_id,
            "speaker": u.speaker,
            "text": u.clean_text.replace(r"\N", " ").replace("\n", " ").strip(),
        }
        for u in group
    ]

    prompt = (
        f"Synopsis: {synopsis}\n"
        f"Known characters with genders and aliases:\n{json.dumps(char_list, ensure_ascii=False)}\n\n"
        "Analyze the dialogue lines below. Maintain consistent speaker attribution across multi-line statements.\n"
        "For each line, determine:\n"
        "- speaker: character name\n"
        "- listener: intended listener/interlocutor\n"
        "- confidence: 'high' (known main/supporting character), 'medium', or 'low' (unknown/crowd)\n"
        "- tone: emotional tone of the speaker (e.g. sarcastic, serious, angry, joyful)\n"
        "- relationship: brief description of their relationship\n"
        "- challenges: list of linguistic challenges (e.g. puns, honorifics, cultural references)\n\n"
        f"Lines:\n{json.dumps(lines_payload, ensure_ascii=False)}"
    )

    instructions = (
        "You are an expert anime director and subtitle dialogue analyst. "
        "Analyze dialogue scenes and output valid JSON matching the requested schema.\n\n"
        "CRITICAL GUIDELINES FOR DIALOGUE FLOW AND TURN-TAKING:\n"
        "1. NO AUTOMATIC ALTERNATION: Subtitle events often split a single character's speech "
        "across multiple consecutive lines. Do NOT assume speakers alternate every line (A -> B -> A -> B). "
        "A single character frequently speaks 2, 3, or more consecutive lines "
        "(monologues, explanations, rants, multi-sentence thoughts).\n"
        "2. SEMANTIC CONTINUITY: If line N+1 elaborates, explains, justifies, or continues the emotional "
        "thought of line N without an explicit response from another character, it is spoken by the SAME character.\n"
        "3. VOCATIVE RESOLUTION: When a character addresses someone by name or nickname "
        "(e.g. 'Takagi, why do you...', 'You wouldn't understand, Takashi', 'Relax, Taka'):\n"
        "   - The named character is the LISTENER of that line, NEVER the speaker.\n"
        "   - In a two-person conversation, the speaker is the other interlocutor.\n"
        "   - The next line is often the response spoken by the named character.\n"
        "4. MULTI-LINE MONOLOGUES: When a character is teasing, insulting, lecturing, or scolding another "
        "(e.g. developing a point across several sentences), keep the speaker consistent across all those "
        "sentences until the interlocutor actually replies or interrupts."
    )

    result = SceneAnalysisDoc()
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
            result = client.generate(req).output
        elif hasattr(client, "complete"):
            raw = client.complete(prompt)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            result = SceneAnalysisDoc.model_validate(json.loads(m.group(0))) if m else SceneAnalysisDoc()
        elif callable(client):
            raw = client(prompt)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            result = SceneAnalysisDoc.model_validate(json.loads(m.group(0))) if m else SceneAnalysisDoc()
    except Exception as exc:
        first = group[0].composite_id if group else "?"
        logger.warning(
            "Falha na análise de cena por IA (bloco a partir de %s): %s. Adotando fallback de baixa confiança.",
            first,
            exc,
        )
        result = SceneAnalysisDoc()

    if known_names:
        _apply_vocative_safeguard(result, group, known_names)

    return result


def analyze_scenes_multimodal(
    merged_doc: MergedUnitsDoc,
    scenes: list[Scene],
    characters: list[CharacterEntry],
    voice_bank: Any | None = None,
    episode_segments: Mapping[str, Any] | None = None,
    synopsis: str = "",
    client: Any | None = None,
    model: str = "review",
    unit_events: Mapping[str, list[int]] | None = None,
    max_lines_per_call: int = 40,
) -> SceneAnalysisDoc:
    """Executa a análise de cena textual e enriquece com a correspondência acústica de centróides de voz."""
    from translaterany.media.audio.clustering import cosine_distance

    base_doc = analyze_scenes(
        merged_doc=merged_doc,
        scenes=scenes,
        characters=characters,
        synopsis=synopsis,
        client=client,
        model=model,
        unit_events=unit_events,
        max_lines_per_call=max_lines_per_call,
    )

    if not voice_bank or not getattr(voice_bank, "profiles", None) or not episode_segments:
        return base_doc

    known_names = _build_known_names(characters)
    updated_lines = dict(base_doc.lines)

    for unit in merged_doc.units:
        ctx = updated_lines.get(unit.composite_id)
        if not ctx:
            continue

        seg = episode_segments.get(unit.composite_id)
        if not seg:
            for uid in unit.unit_ids:
                if uid in episode_segments:
                    seg = episode_segments[uid]
                    break

        if not seg or not getattr(seg, "embedding", None) or not any(x != 0 for x in seg.embedding):
            continue

        best_profile = None
        best_sim = -1.0
        for prof in voice_bank.profiles:
            if not prof.centroid:
                continue
            dist = cosine_distance(seg.embedding, prof.centroid)
            sim = 1.0 - dist
            if sim > best_sim:
                best_sim = sim
                best_profile = prof

        addressed = _extract_vocative(unit.clean_text, known_names) if known_names else None

        if best_profile and best_sim >= 0.80:
            speaker_candidate = best_profile.character_name
            if addressed and speaker_candidate == addressed:
                ctx.speaker = "Unknown"
                ctx.listener = addressed
                ctx.confidence = "medium"
            else:
                ctx.speaker = speaker_candidate
                ctx.confidence = "high"
                if addressed and ctx.listener == "Unknown":
                    ctx.listener = addressed
        elif getattr(seg, "acoustic_gender", None) in ("male", "female"):
            ctx.confidence = "medium"
            if addressed and ctx.listener == "Unknown":
                ctx.listener = addressed

        updated_lines[unit.composite_id] = ctx

    return SceneAnalysisDoc(lines=updated_lines)

