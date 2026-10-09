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
    # Campos determinísticos (artefatos antigos carregam com os padrões abaixo).
    speaker_gender: Literal["male", "female", "unknown"] = "unknown"  # gênero do personagem falante, se conhecido
    speaker_source: str = "llm"  # llm | voice | continuation | self_introduction | fallback
    gender_unsafe: bool = False  # concordância de gênero na tradução não é confiável (triagem de revisão)


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


# Seguem a mesma convenção de merge.py: pontuação final fecha a frase; reticências e vírgula a deixam aberta.
_TERMINAL = (".", "!", "?", "—", "”", '"', "。", "！", "？")
_OPEN_ENDINGS = ("...", "…", ",", ";", ":", "-", "--")
_CONTINUATION_MAX_GAP_MS = 800
_PRIOR_LINES = 3
_SELF_INTRO = re.compile(r"^(?:i'm|i am|my name is|name's)\s+([a-z]+(?:\s+[a-z]+)?)\s*(?:[,.!?;:]|$)", re.IGNORECASE)


def _name_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", text.lower()) if len(t) >= 3]


class _NameResolver:
    """Resolve um nome (completo, apelido ou parte) para o personagem canônico, só quando não há ambiguidade."""

    def __init__(self, characters: list[CharacterEntry]) -> None:
        self.names = {c.name for c in characters}
        self.exact: dict[str, str] = {}
        self.owners: dict[str, set[str]] = {}
        for c in characters:
            for label in [c.name, *c.aliases]:
                self.exact.setdefault(label.lower().strip(), c.name)
                for tok in _name_tokens(label):
                    self.owners.setdefault(tok, set()).add(c.name)
        self.gender: dict[str, str] = {}
        for c in characters:
            g = c.gender.value if hasattr(c.gender, "value") else str(c.gender)
            self.gender[c.name] = g if g in ("male", "female") else "unknown"

    def resolve(self, name: str) -> str | None:
        if name in self.names:
            return name
        hit = self.exact.get(name.lower().strip())
        if hit:
            return hit
        sets = [self.owners[t] for t in _name_tokens(name) if t in self.owners]
        if not sets:
            return None
        common = set.intersection(*sets)
        return next(iter(common)) if len(common) == 1 else None


def _is_continuation(prev_text: str, text: str) -> bool:
    """Frase anterior aberta E fala atual começando em minúscula/reticências (E, não OU: evita falso positivo)."""
    prev = prev_text.strip()
    cur = text.strip()
    if not prev or not cur:
        return False
    prev_open = prev.endswith(_OPEN_ENDINGS) or not prev.endswith(_TERMINAL)
    cur_continues = cur.startswith(("...", "…")) or cur[0].islower()
    return prev_open and cur_continues


def _gap_ms(prev_id: str, cur_id: str, times: Mapping[str, tuple[int, int]]) -> int | None:
    prev, cur = times.get(prev_id), times.get(cur_id)
    return None if prev is None or cur is None else cur[0] - prev[1]


def _finalize_contexts(
    doc: SceneAnalysisDoc,
    merged_doc: MergedUnitsDoc,
    characters: list[CharacterEntry],
    scene_of: Mapping[str, int],
    unit_times: Mapping[str, tuple[int, int]] | None,
) -> SceneAnalysisDoc:
    """Passo determinístico final: normaliza nomes, resolve falantes só com evidência forte e marca o risco de
    gênero. Alternância pelo ouvinte anterior NÃO é usada: medido em episódios reais acerta ~50%.
    Palpites nunca viram confiança 'high'."""
    resolver = _NameResolver(characters)
    known_names = _build_known_names(characters)
    prev: tuple[CompositeUnit, LineContext] | None = None
    for unit in merged_doc.units:
        ctx = doc.lines.get(unit.composite_id)
        if ctx is None:
            continue
        for attr in ("speaker", "listener"):
            value = getattr(ctx, attr)
            canon = resolver.resolve(value) if value != "Unknown" else None
            if canon:
                setattr(ctx, attr, canon)

        if ctx.speaker == "Unknown":
            addressed = _extract_vocative(unit.clean_text, known_names) if known_names else None
            intro = _SELF_INTRO.match(unit.clean_text.strip().replace("’", "'"))
            introduced = resolver.resolve(intro.group(1)) if intro else None
            if introduced and introduced != addressed:
                ctx.speaker, ctx.speaker_source = introduced, "self_introduction"
                ctx.confidence = "medium"
            elif prev is not None and _continues_speaker(prev, unit, ctx, addressed, scene_of, unit_times):
                prev_ctx = prev[1]
                ctx.speaker, ctx.speaker_source = prev_ctx.speaker, "continuation"
                ctx.confidence = "medium"
                if ctx.listener == "Unknown" and prev_ctx.listener != ctx.speaker:
                    ctx.listener = prev_ctx.listener

        if ctx.speaker == "Unknown":
            ctx.confidence = "low"
        ctx.speaker_gender = resolver.gender.get(ctx.speaker, "unknown")  # type: ignore[assignment]
        ctx.gender_unsafe = ctx.speaker_gender == "unknown"
        prev = (unit, ctx)
    return doc


def _continues_speaker(
    prev: tuple[CompositeUnit, LineContext],
    unit: CompositeUnit,
    ctx: LineContext,
    addressed: str | None,
    scene_of: Mapping[str, int],
    unit_times: Mapping[str, tuple[int, int]] | None,
) -> bool:
    prev_unit, prev_ctx = prev
    if prev_ctx.speaker == "Unknown" or prev_ctx.confidence != "high":
        return False
    if prev_ctx.speaker_source not in ("llm", "voice"):
        return False
    if addressed == prev_ctx.speaker:  # chamar o falante anterior pelo nome indica troca de turno
        return False
    if scene_of.get(prev_unit.composite_id) != scene_of.get(unit.composite_id):
        return False
    if not _is_continuation(prev_unit.clean_text, unit.clean_text):
        return False
    if unit_times is not None:
        gap = _gap_ms(prev_unit.composite_id, unit.composite_id, unit_times)
        if gap is None or not -500 <= gap <= _CONTINUATION_MAX_GAP_MS:
            return False
    return True


def _composite_times(
    merged_doc: MergedUnitsDoc, unit_times: Mapping[str, tuple[int, int]] | None
) -> dict[str, tuple[int, int]] | None:
    if unit_times is None:
        return None
    result: dict[str, tuple[int, int]] = {}
    for u in merged_doc.units:
        spans = [unit_times[i] for i in u.unit_ids if i in unit_times]
        if spans:
            result[u.composite_id] = (min(s[0] for s in spans), max(s[1] for s in spans))
    return result


def analyze_scenes(
    merged_doc: MergedUnitsDoc,
    scenes: list[Scene],
    characters: list[CharacterEntry],
    synopsis: str = "",
    client: Any | None = None,
    model: str = "review",
    unit_events: Mapping[str, list[int]] | None = None,
    max_lines_per_call: int = 40,
    unit_times: Mapping[str, tuple[int, int]] | None = None,
) -> SceneAnalysisDoc:
    """Uma chamada por cena (cenas longas em blocos de `max_lines_per_call`). O episódio inteiro numa
    chamada só estoura o contexto de modelos locais; uma falha afeta só a própria cena.
    `unit_times` (id de unidade -> (início, fim) em ms) habilita a checagem de intervalo na continuação."""
    doc, scene_of = _analyze_raw(
        merged_doc, scenes, characters, synopsis, client, model, unit_events, max_lines_per_call
    )
    return _finalize_contexts(doc, merged_doc, characters, scene_of, _composite_times(merged_doc, unit_times))


def _analyze_raw(
    merged_doc: MergedUnitsDoc,
    scenes: list[Scene],
    characters: list[CharacterEntry],
    synopsis: str,
    client: Any | None,
    model: str,
    unit_events: Mapping[str, list[int]] | None,
    max_lines_per_call: int,
) -> tuple[SceneAnalysisDoc, dict[str, int]]:
    fallback_lines: dict[str, LineContext] = {
        u.composite_id: LineContext(
            speaker=u.speaker or "Unknown",
            listener="Unknown",
            confidence="low",
            tone="neutral",
            challenges=[],
            speaker_source="fallback",
        )
        for u in merged_doc.units
    }

    if client is None or not merged_doc.units:
        return SceneAnalysisDoc(lines=fallback_lines), {}

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
    prev_group: list[str] = []
    for id_group in group_by_scene(ids, scene_of, max_lines_per_call):
        group = [by_id[i] for i in id_group]
        # bloco seguinte da mesma cena herda as últimas falas já analisadas (sem isso o falante se perde na fronteira)
        same_scene = bool(prev_group) and scene_of.get(prev_group[0]) == scene_of.get(id_group[0])
        prior = [(by_id[i], final_lines[i]) for i in prev_group[-_PRIOR_LINES:]] if same_scene else []
        parsed = _analyze_group(group, char_list, synopsis, client, model, known_names, prior)
        for k, v in parsed.lines.items():
            if k in final_lines and k in id_group:
                final_lines[k] = v
        prev_group = id_group
    return SceneAnalysisDoc(lines=final_lines), scene_of


def _analyze_group(
    group: list[CompositeUnit],
    char_list: list[dict[str, Any]],
    synopsis: str,
    client: Any,
    model: str,
    known_names: dict[str, str] | None = None,
    prior: list[tuple[CompositeUnit, LineContext]] | None = None,
) -> SceneAnalysisDoc:
    lines_payload = [
        {
            "id": u.composite_id,
            "speaker": u.speaker,
            "text": u.clean_text.replace(r"\N", " ").replace("\n", " ").strip(),
        }
        for u in group
    ]

    prior_block = ""
    if prior:
        prior_payload = [
            {"speaker": ctx.speaker, "text": u.clean_text.replace(r"\N", " ").replace("\n", " ").strip()}
            for u, ctx in prior
        ]
        prior_block = (
            "Previous lines of the same scene (already analyzed; context only, do NOT output them):\n"
            f"{json.dumps(prior_payload, ensure_ascii=False)}\n\n"
        )

    prompt = (
        f"Synopsis: {synopsis}\n"
        f"Known characters with genders and aliases:\n{json.dumps(char_list, ensure_ascii=False)}\n\n"
        "Analyze the dialogue lines below. Maintain consistent speaker attribution across multi-line statements.\n"
        "For each line, determine:\n"
        "- speaker: character name\n"
        "- listener: intended listener/interlocutor\n"
        "- confidence: 'high' (speaker explicit from the text: name, self-reference or clear continuation), "
        "'medium' (plausible but not certain), or 'low' (unknown/crowd)\n"
        "- tone: emotional tone of the speaker (e.g. sarcastic, serious, angry, joyful)\n"
        "- relationship: brief description of their relationship\n"
        "- challenges: list of linguistic challenges (e.g. puns, honorifics, cultural references)\n\n"
        f"{prior_block}"
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
        "sentences until the interlocutor actually replies or interrupts.\n"
        "5. UNKNOWN SPEAKERS: the speaker's gender drives grammatical agreement in the translation, so a wrong "
        "speaker is worse than 'Unknown'. Use 'Unknown' when there is no textual evidence; never fill the gap by "
        "guessing from turn order alone. A guess must be confidence 'low' or 'medium', NEVER 'high'. When "
        "evidence exists (continuation of the previous line, a vocative, self-reference), name the character "
        "instead of leaving 'Unknown'."
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
    unit_times: Mapping[str, tuple[int, int]] | None = None,
) -> SceneAnalysisDoc:
    """Executa a análise de cena textual e enriquece com a correspondência acústica de centróides de voz.
    O gênero acústico isolado NÃO altera a confiança: nos episódios reais ele erra ~50% (quase aleatório) e
    subir para 'medium' escondia o risco de gênero do tradutor."""
    from translaterany.media.audio.clustering import cosine_distance

    base_doc, scene_of = _analyze_raw(
        merged_doc, scenes, characters, synopsis, client, model, unit_events, max_lines_per_call
    )
    times = _composite_times(merged_doc, unit_times)

    if not voice_bank or not getattr(voice_bank, "profiles", None) or not episode_segments:
        return _finalize_contexts(base_doc, merged_doc, characters, scene_of, times)

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
                # a voz casou com quem é chamado pelo nome: o palpite acústico não vale; mantém só um falante
                # do texto que seja outra pessoa
                if ctx.speaker == addressed:
                    ctx.speaker = "Unknown"
                ctx.listener = addressed
            else:
                ctx.speaker = speaker_candidate
                ctx.confidence = "high"
                ctx.speaker_source = "voice"
                if addressed and ctx.listener == "Unknown":
                    ctx.listener = addressed
        elif addressed and ctx.listener == "Unknown":
            ctx.listener = addressed

        updated_lines[unit.composite_id] = ctx

    return _finalize_contexts(SceneAnalysisDoc(lines=updated_lines), merged_doc, characters, scene_of, times)
