"""Módulo de tradução especializada de músicas e canções."""

from __future__ import annotations

import logging
import re

from translaterany.llm.client import LLMClient
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import DialogueBatchTranslator

logger = logging.getLogger(__name__)

SONGS_SYSTEM_INSTRUCTIONS = """Você é um tradutor e letrista especialista de músicas de animes (Inglês para Português do Brasil).
Sua missão é traduzir letras de aberturas, encerramentos e canções de forma poética, lírica e expressiva.
- Produza versos que soem naturais, emotivos e rítmicos em português brasileiro.
- NUNCA traduza tags de karaokê (ex: \\k, \\kf, \\K) nem palavras em romaji ou japonês transliterado.
- Preserve o sentido lírico e poético da canção original.
- Preserve exatamente quaisquer marcadores numéricos como ⟦n⟧ se presentes.
Você DEVE devolver exclusivamente a estrutura solicitada, contendo a tradução de todas as linhas de música
identificadas por seus IDs."""


def translate_songs(
    doc: NormalizedDoc,
    classes: dict[str, UnitClass] | Classification,
    tm_resolved: dict[str, str] | None = None,
    client: LLMClient | None = None,
    model: str = "translate",
    fallback_model: str | None = "translategemma",
    max_tokens_per_batch: int = 800,
    max_lines_per_batch: int | None = 1,
    metrics: StageMetrics | None = None,
) -> UnitTexts:
    """Traduz canções e letras musicais, preservando lírica e ignorando karaokê/romaji."""
    class_map = classes.units if isinstance(classes, Classification) else classes
    tm_map = tm_resolved or {}

    song_units = [
        u
        for u in doc.units
        if u.id in class_map
        and class_map[u.id].type == "song"
        and class_map[u.id].type not in ("karaoke", "romaji")
        and not re.search(r"\\k\d*", u.text, re.IGNORECASE)
    ]

    texts: dict[str, str] = {}
    pending_units: list[DialogueLine] = []

    for u in song_units:
        if u.id in tm_map:
            texts[u.id] = tm_map[u.id]
        else:
            pending_units.append(DialogueLine(id=u.id, text=u.text))

    if not pending_units or client is None:
        return UnitTexts(texts=texts)

    if metrics:
        metrics.count("lines", len(pending_units))

    translator = DialogueBatchTranslator(
        client=client,
        model_name=model,
        fallback_model=fallback_model,
        max_tokens_per_batch=max_tokens_per_batch,
        max_lines_per_batch=max_lines_per_batch,
        max_context_lines=2,
        metrics=metrics,
        system_instructions=SONGS_SYSTEM_INSTRUCTIONS,
    )
    raw_translations = translator.translate_lines(pending_units)

    song_units_by_id = {u.id: u for u in song_units}
    for line in pending_units:
        u = song_units_by_id[line.id]
        tr = raw_translations.get(line.id, u.text)
        expected = list(range(1, u.markers + 1))
        if not expected and ("⟦" in tr or "⟧" in tr):
            tr = tr.replace("⟦", "").replace("⟧", "")
        has_malformed = "⟦" in re.sub(r"⟦\d+⟧", "", tr) or "⟧" in re.sub(r"⟦\d+⟧", "", tr)
        if sorted(marker_ids(tr)) != expected or has_malformed:
            logger.warning(
                "Música %s: tradução perdeu ou corrompeu marcadores %s (obtido %s). Mantendo texto original.",
                u.id,
                expected,
                marker_ids(tr),
            )
            tr = u.text
            if metrics:
                metrics.count("markers_lost")
        texts[u.id] = tr

    return UnitTexts(texts=texts)
