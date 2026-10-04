"""Escolha da faixa de legenda em inglês que serve de base para a tradução."""

import re
from dataclasses import dataclass, field

from translaterany.languages.models import LanguageInfo
from translaterany.languages.registry import LanguageRegistry
from translaterany.media.mkv import IMAGE_CODECS, TEXT_CODECS, MkvInfo, Track

OWN_TRACK_NAME = "Português (Brasil) — TranslaterAny"
_OWN = re.compile(r"translaterany", re.IGNORECASE)
_SDH = re.compile(r"\bsdh\b|\bcc\b|hearing", re.IGNORECASE)
_SIGNS = re.compile(r"sign|song|s&s|forced", re.IGNORECASE)


class NoTrack(Exception):  # noqa: N818 — vira SkipEpisode
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CandidateInfo:
    id: int
    name: str
    kind: str  # full | signs_songs | sdh | own | image | other_language
    discarded: str | None


@dataclass
class Selection:
    chosen: Track
    reason: str
    candidates: list[CandidateInfo]
    sdh_track_ids: list[int]
    own_track_ids: list[int]
    warnings: list[str] = field(default_factory=list)


def is_own(track: Track) -> bool:
    return bool(_OWN.search(track.name))


def is_sdh(track: Track) -> bool:
    return track.hearing_impaired or bool(_SDH.search(track.name))


def is_signs(track: Track) -> bool:
    return track.forced or bool(_SIGNS.search(track.name))


def is_portuguese(track: Track) -> bool:
    lang = track.language.lower()
    return lang.startswith("pt") or lang == "por"


def is_english_or_und(track: Track) -> bool:
    lang = track.language.lower()
    return lang.startswith("en") or lang in {"eng", "und"}


def is_source_or_und(track: Track, source_lang: LanguageInfo) -> bool:
    lang = track.language.lower()
    return lang in {"und", ""} or LanguageRegistry.matches(track.language, source_lang)


def select_track(
    info: MkvInfo,
    preferred: str | None = None,
    *,
    force: bool = False,
    source_lang: LanguageInfo | None = None,
    target_lang: LanguageInfo | None = None,
) -> Selection:
    if source_lang is None:
        source_lang = LanguageRegistry.resolve("en")
    if target_lang is None:
        target_lang = LanguageRegistry.resolve("pt-BR")

    subs = info.subtitles
    own = [t for t in subs if is_own(t)]
    target_display = "PT-BR" if target_lang.code == "pt-BR" else target_lang.name_pt
    if not force and any(LanguageRegistry.matches(t.language, target_lang) and not is_own(t) for t in subs):
        raise NoTrack(f"já existe legenda {target_display} de outra fonte (use --force para sobrescrever)")
    sdh = [t for t in subs if not is_own(t) and is_sdh(t)]
    infos: list[CandidateInfo] = []
    candidates: list[Track] = []
    source_display = "inglês" if source_lang.code == "en" else source_lang.name_pt
    for track in subs:
        if is_own(track):
            infos.append(CandidateInfo(track.id, track.name, "own", "faixa da própria app"))
        elif track.codec_id in IMAGE_CODECS:
            infos.append(CandidateInfo(track.id, track.name, "image", "legenda em imagem"))
        elif track.codec_id not in TEXT_CODECS or not is_source_or_und(track, source_lang):
            infos.append(
                CandidateInfo(track.id, track.name, "other_language", f"não é legenda de texto em {source_display}")
            )
        elif is_sdh(track):
            infos.append(CandidateInfo(track.id, track.name, "sdh", "SDH/CC nunca é usada como base"))
        else:
            candidates.append(track)

    if not candidates:
        source_text = [
            t for t in subs if t.codec_id in TEXT_CODECS and is_source_or_und(t, source_lang) and not is_own(t)
        ]
        if source_text and all(is_sdh(t) for t in source_text):
            raise NoTrack(f"só há legenda SDH em {source_display}")
        if any(t.codec_id in IMAGE_CODECS for t in subs):
            raise NoTrack("legenda em imagem (OCR fora da v1)")
        raise NoTrack(f"sem legenda em {source_display}")

    warnings: list[str] = []
    chosen: Track | None = None
    reason = ""
    if preferred:
        matches = sorted(
            (t for t in candidates if preferred.lower() in t.name.lower()),
            key=lambda t: (is_signs(t), not t.default, t.id),
        )
        if matches:
            chosen, reason = matches[0], f"escolha manual (series.toml: '{preferred}')"
        else:
            warnings.append(f"series.toml pede faixa com '{preferred}', mas nenhuma candidata corresponde")
    if chosen is None:
        ordered = sorted(candidates, key=lambda t: (is_signs(t), not t.default, t.id))
        chosen = ordered[0]
        full = [t for t in candidates if not is_signs(t)]
        if is_signs(chosen):
            reason = "única opção: faixa de placas e músicas"
        elif len(full) > 1:
            reason = "faixa completa; desempate pela marca default" if chosen.default else "faixa completa; menor ID"
        else:
            reason = "faixa completa (não é de placas/músicas)"
    for track in candidates:
        if track is not chosen:
            why = "preterida: placas/músicas" if is_signs(track) else "preterida no desempate"
            infos.append(CandidateInfo(track.id, track.name, "signs_songs" if is_signs(track) else "full", why))
    infos.append(CandidateInfo(chosen.id, chosen.name, "signs_songs" if is_signs(chosen) else "full", None))
    infos.sort(key=lambda c: c.id)
    return Selection(
        chosen=chosen,
        reason=reason,
        candidates=infos,
        sdh_track_ids=[t.id for t in sdh],
        own_track_ids=[t.id for t in own],
        warnings=warnings,
    )
