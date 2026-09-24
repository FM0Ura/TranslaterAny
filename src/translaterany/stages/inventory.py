"""Etapa inventory: impressão digital de cada arquivo de origem."""

from pydantic import BaseModel

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.util.fs import fingerprint


class InventoryArtifact(BaseModel):
    source: str
    size: int
    fingerprint: str


@register_stage
class InventoryStage(Stage):
    name = "inventory"
    version = "1"
    scope = StageScope.EPISODE
    reads_source = True

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        source = ctx.episode.source
        ctx.output.json(
            InventoryArtifact(source=str(source), size=source.stat().st_size, fingerprint=fingerprint(source))
        )
