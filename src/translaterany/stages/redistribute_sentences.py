"""Etapa redistribute_sentences: redistribui frases compostas e consolida textos finais."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.config.model import AppConfig
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.linebreak import wrap_line
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.redistribute import redistribute_composite_unit
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)



_FIXED = ("normalize", "classify", "translation_memory", "merge_sentences")
_OTHER_TEXTS = ("translate_signs", "translate_songs")


class RedistributeSentencesOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_feed_tm: bool = True


@register_stage
class RedistributeSentencesStage(Stage):
    name: ClassVar[str] = "redistribute_sentences"
    version: ClassVar[str] = "3"  # 3: diálogo da última etapa com produces_dialogue
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    produces_texts: ClassVar[bool] = True
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = RedistributeSentencesOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.max_cpl = 42  # padrão Netflix; o loader aplica o [checks] via bind_pipeline
        self.dialogue_input = "translate_dialogue"
        self.inputs = (*_FIXED, self.dialogue_input, *_OTHER_TEXTS)

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        if app is not None:
            self.max_cpl = app.checks.max_cpl
        dialogue = [s.name for s in previous if s.produces_dialogue]
        if dialogue:
            self.dialogue_input = dialogue[-1]
        self.inputs = (*_FIXED, self.dialogue_input, *_OTHER_TEXTS)

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        return {"max_cpl": self.max_cpl, "dialogue_input": self.dialogue_input}

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
            dialogue_texts = ctx.inputs.json(self.dialogue_input, UnitTexts).texts
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
        markers_by_unit = {u.id: u.markers for u in doc.units}
        if merged_doc and merged_doc.units:
            for comp in merged_doc.units:
                if comp.composite_id in dialogue_texts:
                    translated = dialogue_texts[comp.composite_id]
                    split = redistribute_composite_unit(comp, translated)

                    # Garante que cada unidade desmembrada contenha exatamente os marcadores esperados
                    for uid in comp.unit_ids:
                        exp_cnt = markers_by_unit.get(uid, 0)
                        exp_list = list(range(1, exp_cnt + 1))
                        u_text = split.get(uid, "")
                        u_text = re.sub(r"⟦\s*[nN]\s*⟧", "", u_text)
                        if exp_cnt == 0:
                            if "⟦" in u_text or "⟧" in u_text:
                                split[uid] = u_text.replace("⟦", "").replace("⟧", "").strip()
                            else:
                                split[uid] = u_text.strip()
                        else:
                            curr_markers = marker_ids(u_text)
                            if sorted(curr_markers) != exp_list:
                                clean_u = re.sub(r"⟦\d+⟧", "", u_text).strip()
                                split[uid] = clean_u + "".join(f"⟦{m}⟧" for m in exp_list)

                    final_texts.update(split)
                    if len(comp.unit_ids) > 1:
                        count(ctx, "redistributed")
                elif len(comp.unit_ids) == 1 and comp.composite_id in tm_matched:
                    final_texts[comp.composite_id] = tm_matched[comp.composite_id]


        for uid, txt in dialogue_texts.items():
            if uid not in final_texts and "+" not in uid:
                txt = re.sub(r"⟦\s*[nN]\s*⟧", "", txt)
                if markers_by_unit.get(uid, 0) == 0 and ("⟦" in txt or "⟧" in txt):
                    txt = txt.replace("⟦", "").replace("⟧", "").strip()
                final_texts[uid] = txt

        # 2. Placas
        for uid, txt in signs_texts.items():
            txt = re.sub(r"⟦\s*[nN]\s*⟧", "", txt)
            if markers_by_unit.get(uid, 0) == 0 and ("⟦" in txt or "⟧" in txt):
                txt = txt.replace("⟦", "").replace("⟧", "").strip()
            final_texts[uid] = txt

        # 3. Músicas
        for uid, txt in songs_texts.items():
            txt = re.sub(r"⟦\s*[nN]\s*⟧", "", txt)
            if markers_by_unit.get(uid, 0) == 0 and ("⟦" in txt or "⟧" in txt):
                txt = txt.replace("⟦", "").replace("⟧", "").strip()
            final_texts[uid] = txt

        # 4. TM matches remanescentes (músicas só chegam pelo translate_songs, que pode pulá-las)
        for uid, txt in tm_matched.items():
            u_class = classification.units.get(uid)
            if uid not in final_texts and not (u_class and u_class.type == "song"):
                final_texts[uid] = txt

        # Quebra de linha do diálogo pelo CPL (o modelo recebe a frase sem \N)
        for uid, txt in final_texts.items():
            u_class = classification.units.get(uid)
            if u_class and u_class.type == "dialogue":
                final_texts[uid] = wrap_line(txt, self.max_cpl)

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
                from translaterany.memory.tm import TranslationMemoryStore

                tm_path = store.series_dir(series.key) / "memory" / "translation_memory.yaml"
                tm_store = TranslationMemoryStore(tm_path)
                episode = getattr(ctx, "episode", None)
                ep_id = episode.key if episode is not None else ""

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
                            count(ctx, "tm_fed")

        ctx.output.json(UnitTexts(texts=final_texts))
