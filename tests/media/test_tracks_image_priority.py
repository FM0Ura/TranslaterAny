from translaterany.languages.registry import LanguageRegistry
from translaterany.media.mkv import MkvInfo, Track
from translaterany.media.tracks import select_track


def test_select_track_prefers_full_pgs_over_signs_text() -> None:
    # Cenário comum: faixa de texto com apenas placas/músicas, e faixa PGS completa
    text_signs = Track(id=1, name="English Signs & Songs", language="eng", codec_id="S_TEXT/ASS", forced=True)
    pgs_full = Track(id=2, name="English Subtitles", language="eng", codec_id="S_HDMV/PGS", default=True)
    info = MkvInfo(tracks=[text_signs, pgs_full], duration_ns=1000)

    sel = select_track(info, source_lang=LanguageRegistry.resolve("en"))
    assert sel.chosen.id == 2
    assert sel.chosen.codec_id == "S_HDMV/PGS"


def test_select_track_prefers_full_text_over_full_pgs() -> None:
    # Cenário de desempate: ambas são completas, texto tem prioridade sobre OCR
    text_full = Track(id=1, name="English Full", language="eng", codec_id="S_TEXT/ASS")
    pgs_full = Track(id=2, name="English PGS", language="eng", codec_id="S_HDMV/PGS")
    info = MkvInfo(tracks=[text_full, pgs_full], duration_ns=1000)

    sel = select_track(info, source_lang=LanguageRegistry.resolve("en"))
    assert sel.chosen.id == 1
    assert sel.chosen.codec_id == "S_TEXT/ASS"
