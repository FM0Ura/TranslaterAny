"""Etapa treatment_consistency: unificação de pronomes (você/tu/senhor) e gênero entre personagens (M7)."""

from collections.abc import Sequence
from typing import ClassVar

from translaterany.pipeline.registry import register_stage
from translaterany.refine.treatment import scan_treatment_consistency
from translaterany.stages.refine_base import DialogueRefineStage, RefineData

INSTRUCTIONS = """Você é revisor de legendas de anime (inglês -> português do Brasil) focado em COERÊNCIA DE TRATAMENTO e GÊNERO.
Revise as falas "editavel" que divergiram do padrão de tratamento do par de personagens ou com flexão de gênero incorreta, conforme indicado em "sinais".
Ajuste os pronomes (ex.: unifique para "você" ou "tu" conforme a maioria indicada) e as flexões verbais/adjetivais correspondentes.
NÃO altere o sentido original nem reescreva falas desnecessariamente. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA corrigida em português do Brasil) e "reason" (justificativa curta).
Se nenhuma fala precisar de alteração, retorne a lista "edits" vazia."""


@register_stage
class TreatmentConsistencyStage(DialogueRefineStage):
    name: ClassVar[str] = "treatment_consistency"
    version: ClassVar[str] = "1"
    default_dialogue_input: ClassVar[str] = "colloquial"

    def instructions(self) -> str:
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
        char_gender = {c.name: c.gender for c in data.characters if c.gender}
        report = scan_treatment_consistency(lines_info, character_gender=char_gender)

        targets: dict[str, list[str]] = {}
        for pair_report in report.values():
            for lid, reasons in pair_report.divergent_reasons.items():
                targets[lid] = reasons
        return targets
