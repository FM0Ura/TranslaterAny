from translaterany.library.discovery import is_bazarr_auxiliary_subtitle


def test_bazarr_auxiliary_subtitles():
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.hi.srt") is True
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.forced.ass") is True
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.sdh.srt") is True
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.ass") is False
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.srt") is False
