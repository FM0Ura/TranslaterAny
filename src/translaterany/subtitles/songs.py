"""Módulo de tradução especializada de músicas e canções."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Literal

from translaterany.languages.models import LanguageInfo
from translaterany.llm.client import LLMClient
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import (
    BILINGUAL_LYRIC_RULE,
    Classification,
    UnitClass,
    is_lyric_translation_style,
    style_tokens,
)
from translaterany.subtitles.lyrics import BilingualLyric, split_bilingual_lyric
from translaterany.subtitles.normalize import NormalizedDoc, Unit
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import DialogueBatchTranslator

logger = logging.getLogger(__name__)

# Estilos que carregam a letra original (karaokê/nativo): ficam intactos quando existe linha de tradução
_ORIGINAL_LYRIC_TOKENS = frozenset({"kara", "karaoke"})
_ROMAJI_OR_KARAOKE_TYPES = ("karaoke", "romaji")

BilingualGloss = Literal["translate", "drop", "keep"]

SONGS_SYSTEM_INSTRUCTIONS = """Você é um tradutor e letrista especialista de músicas de animes
(Inglês para Português do Brasil).
Sua missão é traduzir letras de aberturas, encerramentos e canções de forma poética, lírica e expressiva.
- Produza versos que soem naturais, emotivos e rítmicos em português brasileiro.
- NUNCA traduza tags de karaokê (ex: \\k, \\kf, \\K) nem palavras em romaji ou japonês transliterado.
- Preserve o sentido lírico e poético da canção original.
- Preserve exatamente quaisquer marcadores numéricos como ⟦n⟧ se presentes.
Você DEVE devolver exclusivamente a estrutura solicitada, contendo a tradução de todas as linhas de música
identificadas por seus IDs."""


def render_songs_system_instructions(source: LanguageInfo, target: LanguageInfo) -> str:
    target_desc = "português brasileiro" if target.code == "pt-BR" else target.name_pt
    source_title = "Inglês" if source.code == "en" else source.name_pt.title()
    target_title = "Português do Brasil" if target.code == "pt-BR" else target.name_pt.title()
    return (
        f"Você é um tradutor e letrista especialista de músicas de animes ({source_title} para {target_title}).\n"
        "Sua missão é traduzir letras de aberturas, encerramentos e canções de forma poética, lírica e expressiva.\n"
        f"- Produza versos que soem naturais, emotivos e rítmicos em {target_desc}.\n"
        "- NUNCA traduza tags de karaokê (ex: \\k, \\kf, \\K) nem palavras em romaji ou japonês transliterado.\n"
        "- Preserve o sentido lírico e poético da canção original.\n"
        "- Preserve exatamente quaisquer marcadores numéricos como ⟦n⟧ se presentes.\n"
        "Você DEVE devolver exclusivamente a estrutura solicitada, contendo a tradução de todas as linhas de música\n"
        "identificadas por seus IDs."
    )


def select_song_units(
    doc: NormalizedDoc,
    class_map: Mapping[str, UnitClass],
    translate_all: bool = True,
    bilingual_gloss: BilingualGloss = "translate",
) -> tuple[list[Unit], dict[str, BilingualLyric]]:
    """Escolhe o que a etapa de músicas traduz.

    Linhas de tradução de letra ('op trans' ao lado de um estilo de karaokê) e a glosa inglesa de letras
    bilíngues 'romaji\\Ninglês' são sempre tratadas (são tradução, não letra); as demais músicas só com
    translate_all. Devolve as unidades de texto inteiro e, por id, as letras bilíngues já divididas.
    """
    song_units = [
        u
        for u in doc.units
        if u.id in class_map
        and class_map[u.id].type == "song"
        and not re.search(r"\\k\d*", u.text, re.IGNORECASE)
    ]
    has_translation_lines = False
    companions = False
    for u in doc.units:
        ucls = class_map.get(u.id)
        if ucls is None:
            continue
        if ucls.type == "song" and is_lyric_translation_style(u.style):
            has_translation_lines = True
        if ucls.type in _ROMAJI_OR_KARAOKE_TYPES or set(style_tokens(u.style)) & _ORIGINAL_LYRIC_TOKENS:
            companions = True
    translation_lines = has_translation_lines and companions

    whole: list[Unit] = []
    bilingual: dict[str, BilingualLyric] = {}
    for u in song_units:
        lyric = split_bilingual_lyric(u.text) if class_map[u.id].rule == BILINGUAL_LYRIC_RULE else None
        if lyric is not None:
            if bilingual_gloss != "keep":
                bilingual[u.id] = lyric
        elif translation_lines and is_lyric_translation_style(u.style):
            whole.append(u)
        elif translate_all and not (translation_lines and set(style_tokens(u.style)) & _ORIGINAL_LYRIC_TOKENS):
            whole.append(u)
    return whole, bilingual


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
    system_instructions: str | None = None,
    translate_all: bool = True,
    bilingual_gloss: BilingualGloss = "translate",
) -> UnitTexts:
    """Traduz canções e letras musicais, preservando lírica e ignorando karaokê/romaji."""
    class_map = classes.units if isinstance(classes, Classification) else classes
    tm_map = tm_resolved or {}

    song_units, bilingual = select_song_units(doc, class_map, translate_all, bilingual_gloss)

    texts: dict[str, str] = {}
    pending_units: list[DialogueLine] = []

    for u in song_units:
        if u.id in tm_map:
            texts[u.id] = tm_map[u.id]
        else:
            pending_units.append(DialogueLine(id=u.id, text=u.text))

    for uid, lyric in bilingual.items():
        if uid in tm_map:
            texts[uid] = tm_map[uid]
        elif bilingual_gloss == "drop":
            # só o romaji; os marcadores da glosa vão para o fim para a unidade manter todos os seus
            texts[uid] = lyric.romaji + "".join(f"⟦{m}⟧" for m in marker_ids(lyric.gloss))
        else:
            pending_units.append(DialogueLine(id=uid, text=lyric.gloss))

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
        system_instructions=system_instructions or SONGS_SYSTEM_INSTRUCTIONS,
    )
    raw_translations = translator.translate_lines(pending_units)

    for line in pending_units:
        lyric = bilingual.get(line.id)
        original = line.text  # a glosa inteira, no caso das letras bilíngues
        tr = raw_translations.get(line.id, original)
        expected = sorted(marker_ids(original))
        if not expected and ("⟦" in tr or "⟧" in tr):
            tr = tr.replace("⟦", "").replace("⟧", "")
        has_malformed = "⟦" in re.sub(r"⟦\d+⟧", "", tr) or "⟧" in re.sub(r"⟦\d+⟧", "", tr)
        if sorted(marker_ids(tr)) != expected or has_malformed:
            logger.warning(
                "Música %s: tradução perdeu ou corrompeu marcadores %s (obtido %s). Mantendo texto original.",
                line.id,
                expected,
                marker_ids(tr),
            )
            tr = original
            if metrics:
                metrics.count("markers_lost")
        if lyric is not None:
            tr = lyric.romaji + lyric.separator + tr
        texts[line.id] = tr

    return UnitTexts(texts=texts)
