"""Etapa review_meaning: revisão de fidelidade de todas as falas, respondendo só com edições."""

from collections.abc import Sequence
from typing import ClassVar

from translaterany.pipeline.registry import register_stage
from translaterany.refine.triage import meaning_signals
from translaterany.stages.refine_base import DialogueRefineStage, RefineData

INSTRUCTIONS = """Você é revisor de legendas de anime (inglês -> português do Brasil).
Revise SOMENTE a fidelidade de cada fala "editavel": omissões, acréscimos (inclusive ofensas ou palavrões
que não existem no original), sentido trocado, gênero ou número errado quando o contexto deixa claro.
NÃO reescreva estilo nem troque palavras por gosto. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id" (o id da fala), "new" (a fala COMPLETA já corrigida em
português do Brasil, nunca um trecho ou fragmento, mantendo os marcadores ⟦n⟧) e "reason" (justificativa curta).
Respeite "limite_caracteres" quando houver. "sinais" indicam onde há risco. Falas com "editavel": false são
só contexto. Responda apenas com as falas que precisam mudar; se nenhuma precisar, devolva a lista vazia."""


@register_stage
class ReviewMeaningStage(DialogueRefineStage):
    name: ClassVar[str] = "review_meaning"
    version: ClassVar[str] = "1"

    def instructions(self) -> str:
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        signals = meaning_signals(data.lines, data.env)
        return {i: signals.get(i, []) for i in ids}  # todas as falas; sinais como destaque
