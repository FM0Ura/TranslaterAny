"""Etapa classify: tipo de cada unidade (regras) e cenas de diálogo."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.classify import classify, disambiguate_uncertain_units
from translaterany.subtitles.normalize import NormalizedDoc


class ClassifyOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_gap_ms: int = 5000
    ai_disambiguate: bool = False
    model: str = "review"


@register_stage
class ClassifyStage(Stage):
    name = "classify"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("normalize",)
    Options = ClassifyOptions

    def __init__(self, options: BaseModel | None = None, client: Any = None) -> None:
        super().__init__(options)
        self.client = client

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        return {
            "styles": dict(sorted(series.config.styles.items())),
            "ai_disambiguate": self.options.ai_disambiguate,
        }

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        res = classify(doc, ctx.series.config.styles, self.options.scene_gap_ms)
        client = getattr(self, "client", None) or getattr(ctx, "llm", None)
        if self.options.ai_disambiguate and client is not None:
            res = disambiguate_uncertain_units(
                doc, res, client, model=self.options.model, scene_gap_ms=self.options.scene_gap_ms
            )
            count(ctx, "ai_disambiguated", sum(1 for c in res.units.values() if c.rule == "ai_disambiguate"))
        ctx.output.json(res)

