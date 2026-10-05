"""Etapa write: remonta o .ass com os textos da etapa indicada em text_source."""

import logging
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from translaterany.config.model import AppConfig
from translaterany.pipeline.registry import REGISTRY, register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.ass import parse_ass, render_ass
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import fill, marker_ids
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

ORIGINAL = "normalize"
DEFAULT_SOURCE = "redistribute_sentences"


class WriteOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_source: str = DEFAULT_SOURCE


class TextError(Exception):
    """Texto de uma etapa de tradução não devolveu os marcadores da unidade."""


@register_stage
class WriteStage(Stage):
    name = "write"
    version = "1"
    scope = StageScope.EPISODE
    Options = WriteOptions

    source_stage: str = "extract"

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.source_stage = "extract"
        self._update_inputs()

    def _update_inputs(self) -> None:
        source = self.options.text_source
        base = self.source_stage
        self.inputs = (base, ORIGINAL) if source == ORIGINAL else (base, ORIGINAL, source)

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        stages_by_name = {s.name: s for s in previous}
        if "ocr" in stages_by_name:
            self.source_stage = "ocr"
        else:
            self.source_stage = "extract"

        if "text_source" not in self.options.model_fields_set:
            texts = [s.name for s in previous if s.produces_texts]
            if texts:
                self.options.text_source = texts[-1]

        self._update_inputs()

    def run(self, ctx: StageContext) -> None:
        source = self.options.text_source
        if self.source_stage == "ocr":
            from translaterany.stages.ocr import OCRArtifact

            art = ctx.inputs.json("ocr", OCRArtifact)
            doc = parse_ass(Path(art.path).read_bytes())
        else:
            doc = parse_ass(ctx.inputs.path("extract").read_bytes())
        normalized = ctx.inputs.json(ORIGINAL, NormalizedDoc)
        texts = {} if source == ORIGINAL else ctx.inputs.json(source, UnitTexts).texts
        markers_by_unit = {u.id: u.markers for u in normalized.units}
        new_texts: dict[int, str] = {}
        for ev in normalized.events:
            if ev.unit is None or ev.unit not in texts:
                continue
            text = texts[ev.unit]
            expected = list(range(1, markers_by_unit[ev.unit] + 1))
            if not expected and ("⟦" in text or "⟧" in text):
                text = text.replace("⟦", "").replace("⟧", "")
            has_malformed = "⟦" in re.sub(r"⟦\d+⟧", "", text) or "⟧" in re.sub(r"⟦\d+⟧", "", text)
            if sorted(marker_ids(text)) != expected or has_malformed:
                logger.warning(
                    "unidade %s: marcadores divergentes (esperado %s, obtido %s); revertendo para original",
                    ev.unit,
                    expected,
                    marker_ids(text),
                )
                text = ev.text
            new_texts[ev.index] = ev.prefix + fill(text, ev.markers) + ev.suffix
        translates = source in REGISTRY and REGISTRY.get(source).translates
        changed = any(doc.events[i].text != text for i, text in new_texts.items())
        ctx.output.file(".ass", render_ass(doc, new_texts, marker=translates and changed))
