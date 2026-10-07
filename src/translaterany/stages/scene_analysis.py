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
    version: ClassVar[str] = "3"  # 2: uma chamada por cena; 3: falantes determinísticos + sinal de gênero
    scope: ClassVar[StageScope] = StageScope.EPISODE
    inputs: ClassVar[tuple[str, ...]] = (
        "normalize",
        "classify",
        "consolidate_memory",
        "merge_sentences",
    )
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = SceneAnalysisOptions

    def __init__(self, options: BaseModel | None = None, client: Any = None) -> None:
        super().__init__(options)
        self.client = client

    def bind_pipeline(self, previous: Sequence[Stage], app: Any = None) -> None:
        prev_names = {s.name for s in previous}
        extra = []
        if "extract_voice" in prev_names:
            extra.append("extract_voice")
        if "consolidate_voice_bank" in prev_names:
            extra.append("consolidate_voice_bank")
        self.inputs = (*self.inputs, *extra)

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

        voice_bank = None
        episode_segments = {}
        try:
            from translaterany.media.audio.voice_bank import VoiceBankDoc

            voice_bank = ctx.inputs.json("consolidate_voice_bank", VoiceBankDoc)
        except Exception:
            pass

        try:
            from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact

            voice_art = ctx.inputs.json("extract_voice", VoiceEmbeddingsArtifact)
            episode_segments = {s.unit_id: s for s in voice_art.segments}
        except Exception:
            pass

        unit_events = {u.id: u.events for u in normalized.units}
        event_span = {ev.index: (ev.start_ms, ev.end_ms) for ev in normalized.events}
        unit_times: dict[str, tuple[int, int]] = {}
        for u in normalized.units:
            spans = [event_span[i] for i in u.events if i in event_span]
            if spans:
                unit_times[u.id] = (min(s[0] for s in spans), max(s[1] for s in spans))

        client = self.client or getattr(ctx, "llm", None)
        if voice_bank and episode_segments:
            from translaterany.subtitles.scene_analysis import analyze_scenes_multimodal

            doc = analyze_scenes_multimodal(
                merged_doc=merged_doc,
                scenes=classification.scenes,
                characters=characters,
                voice_bank=voice_bank,
                episode_segments=episode_segments,
                synopsis=synopsis,
                client=client,
                model=self.options.model,
                unit_events=unit_events,
                max_lines_per_call=self.options.max_lines_per_call,
                unit_times=unit_times,
            )
        else:
            doc = analyze_scenes(
                merged_doc=merged_doc,
                scenes=classification.scenes,
                characters=characters,
                synopsis=synopsis,
                client=client,
                model=self.options.model,
                unit_events=unit_events,
                max_lines_per_call=self.options.max_lines_per_call,
                unit_times=unit_times,
            )
        ctx.output.json(doc)
