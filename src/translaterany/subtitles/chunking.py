"""Agrupamento de falas de diálogo em lotes (chunking) com janela de contexto deslizante."""

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from translaterany.memory.models import CharacterEntry, GlossaryEntry


class DialogueLine(BaseModel):
    id: str
    text: str


class ContextLine(BaseModel):
    text: str


@dataclass(frozen=True)
class DialogueBatch:
    lines: list[DialogueLine]
    context: list[ContextLine]


def estimate_tokens(text: str) -> int:
    """Estimativa rápida de tokens (~4 caracteres por token)."""
    return max(1, len(text) // 4)


def create_dialogue_batches(
    lines: list[DialogueLine],
    max_tokens_per_batch: int = 800,
    max_context_lines: int = 5,
    max_lines_per_batch: int | None = None,
) -> list[DialogueBatch]:
    """`max_lines_per_batch=1` manda uma fala por chamada: modelos de tradução pura (TranslateGemma)
    desalinham IDs em lotes, deslocando traduções para a fala vizinha."""
    batches: list[DialogueBatch] = []
    current_lines: list[DialogueLine] = []
    current_tokens = 0
    recent_history: deque[ContextLine] = deque(maxlen=max_context_lines if max_context_lines > 0 else 0)

    for line in lines:
        line_tokens = estimate_tokens(line.text) + 6  # overhead por fala
        full = max_lines_per_batch is not None and len(current_lines) >= max_lines_per_batch
        if current_lines and (full or current_tokens + line_tokens > max_tokens_per_batch):
            context_slice = list(recent_history) if max_context_lines > 0 else []
            batches.append(DialogueBatch(lines=current_lines, context=context_slice))
            if max_context_lines > 0:
                for cl in current_lines:
                    recent_history.append(ContextLine(text=cl.text))
            current_lines = [line]
            current_tokens = line_tokens
        else:
            current_lines.append(line)
            current_tokens += line_tokens

    if current_lines:
        context_slice = list(recent_history) if max_context_lines > 0 else []
        batches.append(DialogueBatch(lines=current_lines, context=context_slice))

    return batches


def format_batch_prompt(
    lines: list[DialogueLine],
    context: list[ContextLine],
    glossary: Sequence[GlossaryEntry] = (),
    characters: Sequence[CharacterEntry] = (),
    line_contexts: Mapping[str, Any] | None = None,
) -> str:
    sections: list[str] = []
    if glossary:
        sections.append("[GLOSSÁRIO OBRIGATÓRIO]:")
        for g in glossary:
            note = f" ({g.notes})" if g.notes else ""
            sections.append(f"- {g.term} -> {g.translation}{note}")
        sections.append("")

    if characters:
        sections.append("[PERSONAGENS]:")
        for c in characters:
            gender_val = c.gender.value if hasattr(c.gender, "value") else str(c.gender)
            details: list[str] = []
            if c.speech_style:
                details.append(c.speech_style)
            if c.notes:
                details.append(c.notes)
            detail_str = f": {'; '.join(details)}" if details else ""
            sections.append(f"- {c.name} ({gender_val}){detail_str}")
        sections.append("")

    if line_contexts:
        has_any = any(line.id in line_contexts for line in lines)
        if has_any:
            sections.append("[CONTEXTO DA CENA E FALANTES]:")
            for line in lines:
                lctx = line_contexts.get(line.id)
                if lctx:
                    notes = []
                    speaker = getattr(lctx, "speaker", None)
                    if speaker and speaker != "Unknown":
                        notes.append(f"falante: {speaker}")
                    listener = getattr(lctx, "listener", None)
                    if listener and listener != "Unknown":
                        notes.append(f"ouvinte: {listener}")
                    tone = getattr(lctx, "tone", None)
                    if tone and tone != "neutral":
                        notes.append(f"tom: {tone}")
                    conf = getattr(lctx, "confidence", None)
                    if conf:
                        notes.append(f"confiança: {conf}")
                    if conf == "low":
                        notes.append("adote formulação neutra / neutral gender")
                    if notes:
                        sections.append(f"- [{line.id}] {', '.join(notes)}")
            sections.append("")

    if context:
        sections.append("[CONTEXTO RECENTE - APENAS LEITURA, NÃO TRADUZIR]:")
        for idx, ctx in enumerate(context, 1):
            sections.append(f"[CTX-{idx}] {ctx.text}")
        sections.append("")

    sections.append("[FALAS A TRADUZIR]:")
    for line in lines:
        sections.append(f"[{line.id}] {line.text}")

    return "\n".join(sections)
