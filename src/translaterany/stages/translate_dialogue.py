import logging
from typing import ClassVar

from pydantic import BaseModel

from translaterany.llm.client import LLMClient
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import Classification, ClassifiedUnit, ClassifiedUnitCollection
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import DialogueBatchTranslator

logger = logging.getLogger(__name__)


@register_stage
class StageTranslateDialogue(Stage):
    name: ClassVar[str] = "translate_dialogue"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify")
    enabled_by_default: ClassVar[bool] = True

    def __init__(
        self,
        client: LLMClient | BaseModel | None = None,
        options: BaseModel | None = None,
    ) -> None:
        if isinstance(client, BaseModel) and options is None:
            options = client
            client = None
        super().__init__(options)
        self.client = client

    def translate_collection(self, collection: ClassifiedUnitCollection) -> ClassifiedUnitCollection:
        dialogue_units = [u for u in collection.units if u.line_type == "dialogue"]
        if not dialogue_units or not self.client:
            return collection

        lines = [DialogueLine(id=u.id, text=u.clean_text) for u in dialogue_units]
        translator = DialogueBatchTranslator(client=self.client)
        translations = translator.translate_lines(lines)

        new_units: list[ClassifiedUnit] = []
        for u in collection.units:
            if u.id in translations:
                tr_text = translations[u.id]
                new_raw = f"{u.prefix}{tr_text}{u.suffix}"
                new_units.append(u.model_copy(update={"clean_text": tr_text, "raw_text": new_raw}))
            else:
                new_units.append(u)

        return ClassifiedUnitCollection(units=new_units)

    def run(self, ctx: StageContext) -> None:
        client = self.client or ctx.llm
        normalized = ctx.inputs.json("normalize", NormalizedDoc)
        classification = ctx.inputs.json("classify", Classification)

        dialogue_units = [
            u
            for u in normalized.units
            if classification.units.get(u.id) and classification.units[u.id].type == "dialogue"
        ]

        if not dialogue_units or not client:
            ctx.output.json(UnitTexts(texts={}))
            return

        lines = [DialogueLine(id=u.id, text=u.text) for u in dialogue_units]
        try:
            translator = DialogueBatchTranslator(client=client)
            translated_texts = translator.translate_lines(lines)
        except Exception as exc:
            logger.warning("Falha na tradução de diálogos: %s. Mantendo textos originais.", exc)
            translated_texts = {}

        final_texts: dict[str, str] = {}
        for u in dialogue_units:
            tr = translated_texts.get(u.id, u.text)
            if u.markers > 0:
                expected = list(range(1, u.markers + 1))
                if sorted(marker_ids(tr)) != expected:
                    logger.warning(
                        "Unidade %s: tradução perdeu marcadores %s (obtido %s). Fazendo fallback para texto original.",
                        u.id,
                        expected,
                        marker_ids(tr),
                    )
                    tr = u.text
            final_texts[u.id] = tr

        ctx.output.json(UnitTexts(texts=final_texts))
