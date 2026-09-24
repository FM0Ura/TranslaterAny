"""Etapa normalize: segmenta os eventos e agrupa textos únicos."""

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.normalize import normalize


@register_stage
class NormalizeStage(Stage):
    name = "normalize"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("extract",)

    def run(self, ctx: StageContext) -> None:
        doc = parse_ass(ctx.inputs.path("extract").read_bytes())
        ctx.output.json(normalize(doc))
