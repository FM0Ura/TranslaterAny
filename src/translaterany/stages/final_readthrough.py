"""Etapa final_readthrough: leitura corrida do diálogo 100% em português por cena (M7)."""

import json
from collections.abc import Sequence
from typing import Any, ClassVar

from translaterany.config.model import FinalReadthroughOptions
from translaterany.languages.models import LanguageInfo
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import StageContext
from translaterany.refine.blocks import ReviewLine
from translaterany.stages.refine_base import DialogueRefineStage, RefineData
from translaterany.subtitles.linebreak import flatten_breaks

INSTRUCTIONS = """Você é um editor sênior de legendas de anime em português do Brasil
focado em LEITURA CORRIDA e fluidez textual.
Leia o diálogo contínuo da cena em português do Brasil.
Avalie o ritmo das falas, a naturalidade das réplicas e a conexão orgânica entre frases consecutivas.
Ajuste SOMENTE o que soar truncado, robótico, mecânico ou estranhamente desconectado do diálogo vizinho.
NÃO invente piadas, ofensas ou mude o sentido da história. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA lapidada em português do Brasil)
e "reason" (justificativa curta).
Se o diálogo da cena já estiver soando natural e fluido, devolva a lista "edits" vazia."""


def render_final_readthrough_instructions(target: LanguageInfo) -> str:
    target_display = "português do Brasil" if target.code == "pt-BR" else target.name_pt
    return f"""Você é um editor sênior de legendas de anime em {target_display}
focado em LEITURA CORRIDA e fluidez textual.
Leia o diálogo contínuo da cena em {target_display}.
Avalie o ritmo das falas, a naturalidade das réplicas e a conexão orgânica entre frases consecutivas.
Ajuste SOMENTE o que soar truncado, robótico, mecânico ou estranhamente desconectado do diálogo vizinho.
NÃO invente piadas, ofensas ou mude o sentido da história. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA lapidada em {target_display})
e "reason" (justificativa curta).
Se o diálogo da cena já estiver soando natural e fluido, devolva a lista "edits" vazia."""


def render_readthrough_prompt(lines: Sequence[ReviewLine | dict[str, Any]], scene_context: str = "") -> str:
    """Monta prompt para leitura corrida contendo apenas o texto em português e o falante."""
    payload = []
    for ln in lines:
        if isinstance(ln, dict):
            payload.append(
                {
                    "id": ln["id"],
                    "falante": ln.get("speaker", "Unknown"),
                    "fala": ln.get("text", ""),
                }
            )
        else:
            payload.append(
                {
                    "id": ln.id,
                    "falante": ln.speaker,
                    "fala": flatten_breaks(ln.target),
                    "editavel": ln.editable,
                }
            )
    return json.dumps(payload, ensure_ascii=False)


@register_stage
class FinalReadthroughStage(DialogueRefineStage):
    name: ClassVar[str] = "final_readthrough"
    version: ClassVar[str] = "2"  # 2: rejeita edição que remove forma canônica do glossário
    default_dialogue_input: ClassVar[str] = "orthography"
    Options: ClassVar[type] = FinalReadthroughOptions

    def instructions(self, ctx: StageContext | None = None) -> str:
        if ctx is not None:
            from translaterany.languages.registry import LanguageRegistry

            target = getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR")
            return render_final_readthrough_instructions(target)
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        # Leitura corrida avalia todas as falas da cena
        return {i: [] for i in ids}

    def render_prompt(self, review: Sequence[ReviewLine]) -> str:
        return render_readthrough_prompt(review)
