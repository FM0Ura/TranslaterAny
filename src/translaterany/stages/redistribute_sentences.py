"""Etapa redistribute_sentences: redistribui frases compostas e consolida textos finais."""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.redistribute import redistribute_composite_unit
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)


class RedistributeSentencesOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_feed_tm: bool = True


@register_stage
class RedistributeSentencesStage(Stage):
    name: ClassVar[str] = "redistribute_sentences"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    inputs: ClassVar[tuple[str, ...]] = (
        "normalize",
        "classify",
        "translation_memory",
        "merge_sentences",
        "translate_dialogue",
        "translate_signs",
        "translate_songs",
    )
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = RedistributeSentencesOptions

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classification = ctx.inputs.json("classify", Classification)

        tm_matched: dict[str, str] = {}
        try:
            tm_artifact = ctx.inputs.json("translation_memory", TranslationMemoryArtifact)
            tm_matched = tm_artifact.matched_units
        except Exception:
            pass

        merged_doc: MergedUnitsDoc | None = None
        try:
            merged_doc = ctx.inputs.json("merge_sentences", MergedUnitsDoc)
        except Exception:
            pass

        dialogue_texts: dict[str, str] = {}
        try:
            dialogue_texts = ctx.inputs.json("translate_dialogue", UnitTexts).texts
        except Exception:
            pass

        signs_texts: dict[str, str] = {}
        try:
            signs_texts = ctx.inputs.json("translate_signs", UnitTexts).texts
        except Exception:
            pass

        songs_texts: dict[str, str] = {}
        try:
            songs_texts = ctx.inputs.json("translate_songs", UnitTexts).texts
        except Exception:
            pass

        final_texts: dict[str, str] = {}

        # 1. Diálogo (redistribui frases unidas)
        if merged_doc and merged_doc.units:
            for comp in merged_doc.units:
                if comp.composite_id in dialogue_texts:
                    translated = dialogue_texts[comp.composite_id]
                    split = redistribute_composite_unit(comp, translated)
                    final_texts.update(split)
                elif len(comp.unit_ids) == 1 and comp.composite_id in tm_matched:
                    final_texts[comp.composite_id] = tm_matched[comp.composite_id]

        for uid, txt in dialogue_texts.items():
            if uid not in final_texts and "+" not in uid:
                final_texts[uid] = txt

        # 2. Placas
        final_texts.update(signs_texts)

        # 3. Músicas
        final_texts.update(songs_texts)

        # 4. TM matches remanescentes
        for uid, txt in tm_matched.items():
            if uid not in final_texts:
                final_texts[uid] = txt

        # 5. Auto-alimentação da TM da série para músicas e placas traduzidas
        if self.options.auto_feed_tm:
            store = getattr(ctx, "store", None)
            if store is None:
                store = getattr(getattr(ctx, "inputs", None), "_store", None)
            if store is None:
                from translaterany.config.loader import default_data_dir

                store = ArtifactStore(default_data_dir())

            series = getattr(ctx, "series", None)
            if series is not None and store is not None:
                from translaterany.memory.tm import TMEntrySource, TranslationMemoryStore

                tm_path = store.series_dir(series.key) / "memory" / "translation_memory.yaml"
                tm_store = TranslationMemoryStore(tm_path)
                episode = getattr(ctx, "episode", None)
                ep_id = getattr(episode, "id", "") if episode else ""

                for u in doc.units:
                    u_class = classification.units.get(u.id)
                    if not u_class:
                        continue
                    cat = u_class.type
                    if cat in ("sign", "song"):
                        tr = final_texts.get(u.id)
                        if tr and tr != u.text:
                            tm_store.record_translation(
                                clean_text=u.text,
                                translation=tr,
                                category=cat,
                                episode_key=ep_id,
                            )

        ctx.output.json(UnitTexts(texts=final_texts))
