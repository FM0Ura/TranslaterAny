"""Etapa classify: tipo de cada unidade (regras) e cenas de diálogo."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.classify import classify
from translaterany.subtitles.normalize import NormalizedDoc


class ClassifyOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_gap_ms: int = 5000


@register_stage
class ClassifyStage(Stage):
    name = "classify"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("normalize",)
    Options = ClassifyOptions

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        return {"styles": dict(sorted(series.config.styles.items()))}

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        ctx.output.json(classify(doc, ctx.series.config.styles, self.options.scene_gap_ms))
