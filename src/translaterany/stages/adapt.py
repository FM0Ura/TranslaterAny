"""Etapa adapt: condensação de falas que ultrapassam a velocidade de leitura (CPS > 17) (M7)."""

from collections.abc import Sequence
from typing import ClassVar

from translaterany.checks.text import plain
from translaterany.config.model import AdaptOptions
from translaterany.pipeline.registry import register_stage
from translaterany.stages.refine_base import DialogueRefineStage, RefineData

INSTRUCTIONS = """Você é revisor de legendas de anime (inglês -> português do Brasil) focado em VELOCIDADE DE LEITURA (CPS).
Encurte as falas "editavel" para que caibam no orçamento estrito de caracteres indicado em "limite_caracteres".
Preserve o sentido essencial, fatos-chave e o tom original do personagem ao condensar.
NUNCA adicione palavrões, ofensas ou gírias pesadas não presentes na fala original.
Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA encurtada em português do Brasil) e "reason" (justificativa curta).
Se nenhuma fala precisar de alteração, retorne a lista "edits" vazia."""


def identify_cps_exceeded(text: str, duration_ms: int, max_cps: float = 17.0) -> tuple[bool, int]:
    """Verifica se o texto ultrapassa o CPS máximo e devolve (estourou, orcamento_chars)."""
    duration_s = max(0.1, duration_ms / 1000.0)
    budget = int(max_cps * duration_s)
    clean_len = len(plain(text))
    return clean_len > budget, budget


@register_stage
class AdaptStage(DialogueRefineStage):
    name: ClassVar[str] = "adapt"
    version: ClassVar[str] = "1"
    default_dialogue_input: ClassVar[str] = "treatment_consistency"
    Options: ClassVar[type] = AdaptOptions

    def instructions(self) -> str:
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        lines_by_id = {line.id: line for line in data.lines}
        targets: dict[str, list[str]] = {}

        for i in ids:
            src = data.sources.get(i)
            line = lines_by_id.get(i)
            if not src or not line:
                continue
            exceeded, budget = identify_cps_exceeded(line.target, src.duration_ms, self.max_cps)
            if exceeded:
                targets[i] = [f"CPS estourado ({len(plain(line.target))} caracteres > orçamento {budget})"]

        return targets
