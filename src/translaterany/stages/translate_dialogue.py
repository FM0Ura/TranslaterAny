from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from translaterany.llm.client import LLMClient
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import ClassifiedUnit, ClassifiedUnitCollection
from translaterany.subtitles.translator import DialogueBatchTranslator


@register_stage
class StageTranslateDialogue(Stage):
    name: ClassVar[str] = "translate_dialogue"
    version: ClassVar[str] = "1"
    scope: ClassVar[str] = StageScope.EPISODE.value
    translates: ClassVar[bool] = True
    inputs: ClassVar[list[str]] = ["classify"]
    enabled_by_default: ClassVar[bool] = True

    def __init__(
        self,
        client: LLMClient | BaseModel | None = None,
        options: BaseModel | dict[str, Any] | None = None,
    ) -> None:
        if isinstance(client, BaseModel) and options is None:
            options = client
            client = None
        elif isinstance(options, dict):
            options = None
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
                # Reinsere prefixos/sufixos de tags
                new_raw = f"{u.prefix}{tr_text}{u.suffix}"
                new_units.append(u.model_copy(update={"clean_text": tr_text, "raw_text": new_raw}))
            else:
                new_units.append(u)

        return ClassifiedUnitCollection(units=new_units)

    def run(self, ctx: StageContext) -> Path | None:
        if self.client is None and hasattr(ctx, "llm"):
            self.client = ctx.llm

        input_artifacts = getattr(ctx, "input_artifacts", None)
        if isinstance(input_artifacts, dict) and "classify" in input_artifacts:
            input_file = input_artifacts["classify"]
            data = input_file.read_text(encoding="utf-8")
            collection = ClassifiedUnitCollection.model_validate_json(data)
        elif hasattr(ctx, "inputs"):
            try:
                collection = ctx.inputs.json("classify", ClassifiedUnitCollection)
            except Exception:
                input_path = ctx.inputs.path("classify")
                data = input_path.read_text(encoding="utf-8")
                collection = ClassifiedUnitCollection.model_validate_json(data)
        else:
            raise ValueError("Contexto não possui entradas válidas para a etapa")

        translated = self.translate_collection(collection)

        out_path: Path | None = None
        if hasattr(ctx, "artifact_dir"):
            out_path = ctx.artifact_dir / "translated_units.json"
            out_path.write_text(translated.model_dump_json(indent=2), encoding="utf-8")

        if hasattr(ctx, "output") and ctx.output is not None:
            ctx.output.json(translated)
            if out_path is None and hasattr(ctx.output, "path"):
                out_path = ctx.output.path

        return out_path
