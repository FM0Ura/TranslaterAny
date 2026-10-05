from collections.abc import Sequence
from pathlib import Path
from typing import Any

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
    source_stage = "extract"

    def bind_pipeline(self, previous: Sequence[Stage], app: Any = None) -> None:
        prev_names = [s.name for s in previous]
        if "ocr" in prev_names:
            self.source_stage = "ocr"
        else:
            self.source_stage = "extract"
        self.inputs = (self.source_stage,)

    def run(self, ctx: StageContext) -> None:
        source_path = ctx.inputs.path(self.source_stage)
        if self.source_stage == "ocr" and source_path.suffix == ".json":
            from translaterany.stages.ocr import OCRArtifact

            art = ctx.inputs.json("ocr", OCRArtifact)
            ass_bytes = Path(art.path).read_bytes()
        else:
            ass_bytes = source_path.read_bytes()

        doc = parse_ass(ass_bytes)
        ctx.output.json(normalize(doc))
