"""Etapa treatment_consistency: unificação de pronomes (você/tu/senhor) e gênero entre personagens (M7)."""

from collections.abc import Sequence
from typing import ClassVar

from translaterany.config.model import TreatmentConsistencyOptions
from translaterany.languages.models import LanguageInfo
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import StageContext
from translaterany.refine.treatment import scan_treatment_consistency
from translaterany.stages.refine_base import DialogueRefineStage, RefineData

INSTRUCTIONS = """Você é revisor de legendas de anime (inglês -> português do Brasil)
focado em COERÊNCIA DE TRATAMENTO e GÊNERO.
Revise as falas "editavel" que divergiram do padrão de tratamento do par de personagens ou com flexão de gênero/artigos
incorreta, conforme indicado em "sinais".
Ajuste os pronomes (ex.: unifique para "você" ou "tu" conforme a maioria indicada) e as flexões verbais/adjetivais
correspondentes.
Corrija também artigos definidos/indefinidos e possessivos quando associados a personagens ou títulos
femininos/masculinos indicados em sinais (ex.: substitua "o presidente"/"do presidente"/"nosso presidente"
por "a presidente"/"da presidente"/"nossa presidente" quando se referir a uma mulher).
NÃO altere o sentido original nem reescreva falas desnecessariamente. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA corrigida em português do Brasil)
e "reason" (justificativa curta).
Se nenhuma fala precisar de alteração, retorne a lista "edits" vazia."""


def render_treatment_instructions(source: LanguageInfo, target: LanguageInfo) -> str:
    target_display = "português do Brasil" if target.code == "pt-BR" else target.name_pt
    return f"""Você é revisor de legendas de anime ({source.name_pt} -> {target_display})
focado em COERÊNCIA DE TRATAMENTO e GÊNERO.
Revise as falas "editavel" que divergiram do padrão de tratamento do par de personagens ou com flexão de gênero/artigos
incorreta, conforme indicado em "sinais".
Ajuste os pronomes (ex.: unifique para "você" ou "tu" conforme a maioria indicada) e as flexões verbais/adjetivais
correspondentes.
Corrija também artigos definidos/indefinidos e possessivos quando associados a personagens ou títulos
femininos/masculinos indicados em sinais (ex.: substitua "o presidente"/"do presidente"/"nosso presidente"
por "a presidente"/"da presidente"/"nossa presidente" quando se referir a uma mulher).
NÃO altere o sentido original nem reescreva falas desnecessariamente. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA corrigida em {target_display})
e "reason" (justificativa curta).
Se nenhuma fala precisar de alteração, retorne a lista "edits" vazia."""


@register_stage
class TreatmentConsistencyStage(DialogueRefineStage):
    name: ClassVar[str] = "treatment_consistency"
    version: ClassVar[str] = "1"
    default_dialogue_input: ClassVar[str] = "colloquial"
    Options: ClassVar[type] = TreatmentConsistencyOptions

    def instructions(self, ctx: StageContext | None = None) -> str:
        if ctx is not None:
            from translaterany.languages.registry import LanguageRegistry

            source = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
            target = getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR")
            return render_treatment_instructions(source, target)
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        lines_info = [
            {
                "id": line.id,
                "text": line.target,
                "speaker": data.speaker_of.get(line.id, "Unknown"),
                "listener": data.listener_of.get(line.id, "Unknown"),
                "confidence": data.confidence_of.get(line.id, "low"),
            }
            for line in data.lines
            if line.id in ids
        ]
        char_gender: dict[str, str] = {}
        for c in data.characters:
            if not c.gender:
                continue
            g_val = c.gender.value if hasattr(c.gender, "value") else str(c.gender)
            if g_val.lower() in ("gender.unknown", "unknown"):
                continue
            char_gender[c.name] = g_val
            for alias in getattr(c, "aliases", []) or []:
                if alias and alias not in char_gender:
                    char_gender[alias] = g_val

        if data.profile is not None:
            rep = data.profile.scan_treatment(lines_info, character_gender=char_gender)
            targets: dict[str, list[str]] = {}
            for lid, reasons in rep.divergent_reasons.items():
                targets[lid] = reasons if isinstance(reasons, list) else [str(reasons)]
            return targets

        report = scan_treatment_consistency(lines_info, character_gender=char_gender)

        targets = {}
        for pair_report in report.values():
            for lid, reasons in pair_report.divergent_reasons.items():
                targets[lid] = reasons
        return targets
