"""Etapa colloquial: naturalidade PT-BR só nas falas triadas, sem mudar o sentido."""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from translaterany.languages.models import LanguageInfo
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext
from translaterany.refine.triage import colloquial_signals
from translaterany.stages.refine_base import DialogueRefineStage, RefineData
from translaterany.subtitles.texts import UnitTexts

INSTRUCTIONS = """Você é adaptador de legendas de anime para português do Brasil falado.
Deixe cada fala "editavel" mais natural, no tom do personagem ("falante", "tom"), SEM mudar o sentido,
sem acrescentar gírias, ofensas ou palavrões que não existem no original ("en"), dentro de
"limite_caracteres" quando houver. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id" (o id da fala), "new"
(a fala COMPLETA reescrita em português do Brasil, nunca um trecho ou fragmento, mantendo os
marcadores ⟦n⟧) e "reason" (justificativa curta). "sinais" diz por que a fala foi escolhida: formal_connective,
enclisis, redundant_subject e archaic_pronoun = texto duro ou literal demais; too_long = encurtar;
speech_style = ajustar ao jeito de falar do personagem. Falas com
"editavel": false são só contexto. Responda apenas com as falas que mudar; se nenhuma, lista vazia."""


def render_colloquial_instructions(source: LanguageInfo, target: LanguageInfo) -> str:
    target_display = "português do Brasil" if target.code == "pt-BR" else target.name_pt
    source_display = "en" if source.code == "en" else source.code
    return f"""Você é adaptador de legendas de anime para {target_display} falado.
Deixe cada fala "editavel" mais natural, no tom do personagem ("falante", "tom"), SEM mudar o sentido,
sem acrescentar gírias, ofensas ou palavrões que não existem no original ("{source_display}"), dentro de
"limite_caracteres" quando houver. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Responda com a lista "edits"; cada item tem "id" (o id da fala), "new"
(a fala COMPLETA reescrita em {target_display}, nunca um trecho ou fragmento, mantendo os
marcadores ⟦n⟧) e "reason" (justificativa curta). "sinais" diz por que a fala foi escolhida: formal_connective,
enclisis, redundant_subject e archaic_pronoun = texto duro ou literal demais; too_long = encurtar;
speech_style = ajustar ao jeito de falar do personagem. Falas com
"editavel": false são só contexto. Responda apenas com as falas que mudar; se nenhuma, lista vazia."""


@register_stage
class ColloquialStage(DialogueRefineStage):
    name: ClassVar[str] = "colloquial"
    version: ClassVar[str] = "1"
    default_dialogue_input: ClassVar[str] = "review_meaning"

    def __init__(self, options=None) -> None:
        self.pre_review_input: str | None = "translate_dialogue"
        super().__init__(options)

    def _extra_inputs(self) -> tuple[str, ...]:
        if self.pre_review_input and self.pre_review_input != self.dialogue_input:
            return (self.pre_review_input,)
        return ()

    def _bind_extra(self, previous: Sequence[Stage]) -> None:
        names = [s.name for s in previous]
        if "review_meaning" not in names:
            self.pre_review_input = None
            return
        before = previous[: names.index("review_meaning")]
        dialogue = [s.name for s in before if s.produces_dialogue]
        self.pre_review_input = dialogue[-1] if dialogue else None

    def instructions(self, ctx: StageContext | None = None) -> str:
        if ctx is not None:
            from translaterany.languages.registry import LanguageRegistry

            source = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
            target = getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR")
            return render_colloquial_instructions(source, target)
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        styled = {c.name for c in data.characters if c.speech_style}
        if data.profile is not None:
            return data.profile.colloquial_signals(data.lines, data.speaker_of, styled)
        return colloquial_signals(data.lines, data.speaker_of, styled)

    def forbidden_texts(self, ctx: StageContext, texts: Mapping[str, str]) -> dict[str, str] | None:
        if not self.pre_review_input or self.pre_review_input == self.dialogue_input:
            return None
        before = ctx.inputs.json(self.pre_review_input, UnitTexts).texts
        return {i: t for i, t in before.items() if i in texts and texts[i] != t}
