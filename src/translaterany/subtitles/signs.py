"""Módulo de tradução especializada de placas e elementos gráficos visuais."""

from __future__ import annotations

import logging

from translaterany.llm.client import LLMClient
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import DialogueBatchTranslator

logger = logging.getLogger(__name__)

SIGNS_SYSTEM_INSTRUCTIONS = """Você é um tradutor especialista de legendas de animes (Inglês para Português do Brasil).
Sua missão é traduzir placas, textos em tela, avisos e títulos de forma concisa, direta e natural.
- Seja extremamente conciso, pois o texto deve caber no elemento visual da tela.
- Preserve exatamente marcadores de tags ou quebras como ⟦n⟧ sem alterá-los ou removê-los.
- Mantenha termos canônicos e convenções da língua portuguesa (ex: Conselho Estudantil, Sala dos Professores, etc.).
Você DEVE devolver exclusivamente a estrutura solicitada, contendo a tradução de todas as placas/textos
identificados por seus IDs."""


def translate_signs(
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
    """Traduz placas e elementos gráficos visuais, respeitando concisão e marcadores."""
    class_map = classes.units if isinstance(classes, Classification) else classes
    tm_map = tm_resolved or {}

    sign_units = [
        u
        for u in doc.units
        if u.id in class_map and class_map[u.id].type in ("sign", "title")
    ]

    texts: dict[str, str] = {}
    pending_units: list[DialogueLine] = []

    for u in sign_units:
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
        max_context_lines=0,
        metrics=metrics,
        system_instructions=SIGNS_SYSTEM_INSTRUCTIONS,
    )
    raw_translations = translator.translate_lines(pending_units)

    sign_units_by_id = {u.id: u for u in sign_units}
    for line in pending_units:
        u = sign_units_by_id[line.id]
        tr = raw_translations.get(line.id, u.text)
        if u.markers > 0:
            expected = list(range(1, u.markers + 1))
            if sorted(marker_ids(tr)) != expected:
                logger.warning(
                    "Placa %s: tradução perdeu marcadores %s (obtido %s). Mantendo texto original.",
                    u.id,
                    expected,
                    marker_ids(tr),
                )
                tr = u.text
                if metrics:
                    metrics.count("markers_lost")
        texts[u.id] = tr

    return UnitTexts(texts=texts)
