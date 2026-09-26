"""Etapa write: remonta o .ass com os textos da etapa indicada em text_source."""

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.registry import REGISTRY, register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.ass import parse_ass, render_ass
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import fill, marker_ids
from translaterany.subtitles.texts import UnitTexts

ORIGINAL = "normalize"


class WriteOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_source: str = ORIGINAL


class TextError(Exception):
    """Texto de uma etapa de tradução não devolveu os marcadores da unidade."""


@register_stage
class WriteStage(Stage):
    name = "write"
    version = "1"
    scope = StageScope.EPISODE
    Options = WriteOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        source = self.options.text_source
        self.inputs = ("extract", ORIGINAL) if source == ORIGINAL else ("extract", ORIGINAL, source)

    def run(self, ctx: StageContext) -> None:
        source = self.options.text_source
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
            if sorted(marker_ids(text)) != expected:
                raise TextError(f"unidade {ev.unit}: o texto precisa conter exatamente os marcadores {expected}")
            new_texts[ev.index] = ev.prefix + fill(text, ev.markers) + ev.suffix
        translates = source in REGISTRY and REGISTRY.get(source).translates
        changed = any(doc.events[i].text != text for i, text in new_texts.items())
        ctx.output.file(".ass", render_ass(doc, new_texts, marker=translates and changed))
