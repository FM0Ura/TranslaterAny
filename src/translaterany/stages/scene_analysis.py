"""Etapa scene_analysis: infere falantes, ouvintes, tom e desafios da cena."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.config.loader import default_data_dir
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.scene_analysis import analyze_scenes


class SceneAnalysisOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = "review"
    max_lines_per_call: int = 40  # cenas longas são divididas em blocos


@register_stage
class SceneAnalysisStage(Stage):
    name: ClassVar[str] = "scene_analysis"
    version: ClassVar[str] = "2"  # 2: uma chamada por cena
    scope: ClassVar[StageScope] = StageScope.EPISODE
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify", "consolidate_memory", "merge_sentences")
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = SceneAnalysisOptions

    def __init__(self, options: BaseModel | None = None, client: Any = None) -> None:
        super().__init__(options)
        self.client = client

    def run(self, ctx: StageContext) -> None:
        merged_doc = ctx.inputs.json("merge_sentences", MergedUnitsDoc)
        classification = ctx.inputs.json("classify", Classification)
        normalized = ctx.inputs.json("normalize", NormalizedDoc)

        store = getattr(ctx, "store", None)
        if store is None:
            store = getattr(getattr(ctx, "inputs", None), "_store", None)
        if store is None:
            store = ArtifactStore(default_data_dir())

        characters = []
        synopsis = ""
        series = getattr(ctx, "series", None)
        if series is not None and store is not None:
            mem_dir = store.series_dir(series.key) / "memory"
            if mem_dir.exists():
                mem_store = MemoryStore(mem_dir)
                characters = mem_store.load_characters()
                story = mem_store.load_story()
                synopsis = story.synopsis or ""

        client = self.client or getattr(ctx, "llm", None)
        doc = analyze_scenes(
            merged_doc=merged_doc,
            scenes=classification.scenes,
            characters=characters,
            synopsis=synopsis,
            client=client,
            model=self.options.model,
            unit_events={u.id: u.events for u in normalized.units},
            max_lines_per_call=self.options.max_lines_per_call,
        )
        ctx.output.json(doc)
