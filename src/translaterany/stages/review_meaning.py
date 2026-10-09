"""Etapa review_meaning: revisão de fidelidade de todas as falas, respondendo só com edições."""

from collections.abc import Sequence
from typing import ClassVar

from translaterany.languages.models import LanguageInfo
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import StageContext
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


def render_review_meaning_instructions(source: LanguageInfo, target: LanguageInfo) -> str:
    target_display = "português do Brasil" if target.code == "pt-BR" else target.name_pt
    return f"""Você é revisor de legendas de anime ({source.name_pt} -> {target.name_pt}).
Revise SOMENTE a fidelidade de cada fala "editavel": omissões, acréscimos (inclusive ofensas ou palavrões
que não existem no original), sentido trocado, gênero ou número errado quando o contexto deixa claro.
NÃO reescreva estilo nem troque palavras por gosto. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id" (o id da fala), "new" (a fala COMPLETA já corrigida em
{target_display}, nunca um trecho ou fragmento, mantendo os marcadores ⟦n⟧) e "reason" (justificativa curta).
Respeite "limite_caracteres" quando houver. "sinais" indicam onde há risco. Falas com "editavel": false são
só contexto. Responda apenas com as falas que precisam mudar; se nenhuma precisar, devolva a lista vazia."""


@register_stage
class ReviewMeaningStage(DialogueRefineStage):
    name: ClassVar[str] = "review_meaning"
    version: ClassVar[str] = "3"  # 3: glossário casa pelo termo mais longo; 2: rejeita edição que remove forma canônica

    def instructions(self, ctx: StageContext | None = None) -> str:
        if ctx is not None:
            from translaterany.languages.registry import LanguageRegistry

            source = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
            target = getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR")
            return render_review_meaning_instructions(source, target)
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        signals = meaning_signals(data.lines, data.env)
        return {i: signals.get(i, []) for i in ids}  # todas as falas; sinais como destaque
