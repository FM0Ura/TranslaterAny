"""Etapa treatment_consistency: unificação de pronomes (você/tu/senhor) e gênero entre personagens (M7)."""

from collections.abc import Sequence
from typing import Any, ClassVar

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


def render_treatment_instructions(
    source: LanguageInfo, target: LanguageInfo, characters: Sequence[Any] | None = None
) -> str:
    target_display = "português do Brasil" if target.code == "pt-BR" else target.name_pt
    base = f"""Você é revisor de legendas de anime ({source.name_pt} -> {target_display})
focado em COERÊNCIA DE TRATAMENTO e GÊNERO.
Revise as falas "editavel" para garantir a consistência do tratamento (você/tu) e a flexão correta de gênero,
adjetivos, substantivos e artigos entre os personagens interagindo (falante e ouvinte).
Ajuste os pronomes (ex.: unifique para "você" ou "tu" conforme a maioria indicada) e as flexões verbais/adjetivais
correspondentes.
Garanta a concordância de gênero entre falante e ouvinte:
- Quando o falante se referir a si mesmo, flexione adjetivos e particípios no gênero do falante
  (ex.: feminino: "cansada", "mordida", "pronta").
- Quando o falante se dirigir ao ouvinte, flexione no gênero do ouvinte
  (ex.: se o ouvinte for mulher: "aluna exemplar", "burra", "amiga"; se for homem: "aluno exemplar", "burro", "amigo").
Corrija também artigos definidos/indefinidos e possessivos quando associados a personagens ou títulos
femininos/masculinos indicados em sinais (ex.: substitua "o presidente"/"do presidente"/"nosso presidente"
por "a presidente"/"da presidente"/"nossa presidente" quando se referir a uma mulher).
NÃO altere o sentido original nem reescreva falas desnecessariamente. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id", "new" (a fala COMPLETA corrigida em {target_display})
e "reason" (justificativa curta).
Se nenhuma fala precisar de alteração, retorne a lista "edits" vazia."""

    if characters:
        known = []
        for c in characters:
            if not getattr(c, "gender", None) or str(c.gender).lower() in ("unknown", "gender.unknown"):
                continue
            g = "masculino" if str(c.gender).lower() in ("male", "gender.male", "m") else "feminino"
            aliases = [a for a in getattr(c, "aliases", []) or [] if a and a != c.name]
            aliases_str = f" (apelidos: {', '.join(aliases)})" if aliases else ""
            known.append(f"- {c.name}{aliases_str}: {g}")
        if known:
            base += "\n\nPersonagens conhecidos e seus gêneros:\n" + "\n".join(known)

    return base


@register_stage
class TreatmentConsistencyStage(DialogueRefineStage):
    name: ClassVar[str] = "treatment_consistency"
    version: ClassVar[str] = "2"  # 2: rejeita edição que remove forma canônica do glossário
    default_dialogue_input: ClassVar[str] = "colloquial"
    Options: ClassVar[type] = TreatmentConsistencyOptions

    def instructions(self, ctx: StageContext | None = None) -> str:
        if ctx is not None:
            from translaterany.languages.registry import LanguageRegistry
            from translaterany.memory.matching import load_all_characters

            source = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
            target = getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR")
            chars = load_all_characters(getattr(ctx, "store", None), getattr(getattr(ctx, "series", None), "key", ""))
            return render_treatment_instructions(source, target, characters=chars)
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

        signals: dict[str, list[str]] = {}
        if data.profile is not None:
            rep = data.profile.scan_treatment(lines_info, character_gender=char_gender)
            for lid, reasons in rep.divergent_reasons.items():
                signals[lid] = reasons if isinstance(reasons, list) else [str(reasons)]
        else:
            report = scan_treatment_consistency(lines_info, character_gender=char_gender)
            for pair_report in report.values():
                for lid, reasons in pair_report.divergent_reasons.items():
                    signals[lid] = reasons

        return {i: signals.get(i, []) for i in ids}
