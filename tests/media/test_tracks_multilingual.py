# tests/media/test_tracks_multilingual.py
import pytest

from translaterany.languages.registry import LanguageRegistry
from translaterany.media.mkv import MkvInfo, Track
from translaterany.media.tracks import NoTrack, select_track


def test_select_track_by_source_language() -> None:
    tracks = [
        Track(
            id=0,
            type="subtitles",
            codec_id="S_TEXT/ASS",
            name="Dialog",
            language="jpn",
            default=True,
            forced=False,
            hearing_impaired=False,
        ),
        Track(
            id=1,
            type="subtitles",
            codec_id="S_TEXT/ASS",
            name="English",
            language="eng",
            default=False,
            forced=False,
            hearing_impaired=False,
        ),
    ]
    info = MkvInfo(tracks=tuple(tracks), attachments=(), duration_ns=None)

    # Buscando Japonês como origem
    ja = LanguageRegistry.resolve("ja")
    pt = LanguageRegistry.resolve("pt-BR")
    sel_ja = select_track(info, source_lang=ja, target_lang=pt)
    assert sel_ja.chosen.id == 0

    # Buscando Inglês como origem
    en = LanguageRegistry.resolve("en")
    sel_en = select_track(info, source_lang=en, target_lang=pt)
    assert sel_en.chosen.id == 1


def test_collision_check_with_target_language() -> None:
    tracks = [
        Track(
            id=0,
            type="subtitles",
            codec_id="S_TEXT/ASS",
            name="English",
            language="eng",
            default=True,
            forced=False,
            hearing_impaired=False,
        ),
        Track(
            id=1,
            type="subtitles",
            codec_id="S_TEXT/ASS",
            name="Español Latino",
            language="spa",
            default=False,
            forced=False,
            hearing_impaired=False,
        ),
    ]
    info = MkvInfo(tracks=tuple(tracks), attachments=(), duration_ns=None)
    en = LanguageRegistry.resolve("en")
    es = LanguageRegistry.resolve("es")

    # Alvo Espanhol: deve acusar colisão por já existir legenda em espanhol
    with pytest.raises(NoTrack, match="já existe legenda espanhol"):
        select_track(info, source_lang=en, target_lang=es, force=False)

    # Com force=True deve permitir
    sel = select_track(info, source_lang=en, target_lang=es, force=True)
    assert sel.chosen.id == 0
