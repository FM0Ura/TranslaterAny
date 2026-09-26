"""Agrupamento de falas de diálogo em lotes (chunking) com janela de contexto deslizante."""

from dataclasses import dataclass

from pydantic import BaseModel


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
) -> list[DialogueBatch]:
    batches: list[DialogueBatch] = []
    current_lines: list[DialogueLine] = []
    current_tokens = 0
    recent_history: list[ContextLine] = []

    for line in lines:
        line_tokens = estimate_tokens(line.text) + 6  # overhead por fala
        if current_lines and (current_tokens + line_tokens > max_tokens_per_batch):
            context_slice = list(recent_history[-max_context_lines:]) if max_context_lines > 0 else []
            batches.append(DialogueBatch(lines=current_lines, context=context_slice))
            for cl in current_lines:
                recent_history.append(ContextLine(text=cl.text))
            current_lines = [line]
            current_tokens = line_tokens
        else:
            current_lines.append(line)
            current_tokens += line_tokens

    if current_lines:
        context_slice = list(recent_history[-max_context_lines:]) if max_context_lines > 0 else []
        batches.append(DialogueBatch(lines=current_lines, context=context_slice))

    return batches


def format_batch_prompt(lines: list[DialogueLine], context: list[ContextLine]) -> str:
    sections: list[str] = []
    if context:
        sections.append("[CONTEXTO RECENTE - APENAS LEITURA, NÃO TRADUZIR]:")
        for idx, ctx in enumerate(context, 1):
            sections.append(f"[CTX-{idx}] {ctx.text}")
        sections.append("")

    sections.append("[FALAS A TRADUZIR]:")
    for line in lines:
        sections.append(f"[{line.id}] {line.text}")

    return "\n".join(sections)
