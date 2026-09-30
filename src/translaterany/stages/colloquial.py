"""Etapa colloquial: naturalidade PT-BR só nas falas triadas, sem mudar o sentido."""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext
from translaterany.refine.triage import colloquial_signals
from translaterany.stages.refine_base import DialogueRefineStage, RefineData
from translaterany.subtitles.texts import UnitTexts

INSTRUCTIONS = """Você é adaptador de legendas de anime para português do Brasil falado.
Deixe cada fala "editavel" mais natural, no tom do personagem ("falante", "tom"), SEM mudar o sentido,
sem acrescentar gírias, ofensas ou palavrões que não existem no original ("en"), dentro de
"limite_caracteres" quando houver. Mantenha os marcadores ⟦n⟧ exatamente como estão. Falas com
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

    def instructions(self) -> str:
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        styled = {c.name for c in data.characters if c.speech_style}
        return colloquial_signals(data.lines, data.speaker_of, styled)

    def forbidden_texts(self, ctx: StageContext, texts: Mapping[str, str]) -> dict[str, str] | None:
        if not self.pre_review_input or self.pre_review_input == self.dialogue_input:
            return None
        before = ctx.inputs.json(self.pre_review_input, UnitTexts).texts
        return {i: t for i, t in before.items() if i in texts and texts[i] != t}
