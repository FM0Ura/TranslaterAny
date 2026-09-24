"""Seleção de faixa sobre JSONs no formato do `mkvmerge -J` (layouts dos casos de teste reais)."""

import pytest

from translaterany.media.mkv import parse_identify
from translaterany.media.tracks import NoTrack, select_track


def _track(tid: int, name: str, lang: str = "en", codec: str = "S_TEXT/ASS", **flags: bool) -> dict:
    props = {"codec_id": codec, "language": "eng", "language_ietf": lang, "track_name": name}
    props["default_track"] = flags.get("default", False)
    props["forced_track"] = flags.get("forced", False)
    if flags.get("hi"):
        props["flag_hearing_impaired"] = True
    return {"id": tid, "type": "subtitles", "properties": props}


def _info(*subs: dict, attachments: int = 0) -> dict:
    video = {"id": 0, "type": "video", "properties": {"codec_id": "V_MPEGH/ISO/HEVC"}}
    atts = [{"id": i + 1, "file_name": f"f{i}.ttf", "content_type": "font/ttf"} for i in range(attachments)]
    return {
        "container": {"recognized": True, "properties": {"duration": 10**9}},
        "tracks": [video, *subs],
        "attachments": atts,
    }


def _select(*subs: dict, preferred: str | None = None, force: bool = False):
    return select_track(parse_identify(_info(*subs)), preferred, force=force)


def test_parse_identify() -> None:
    info = parse_identify(_info(_track(3, "S&S", default=True), attachments=17))
    assert len(info.attachments) == 17 and info.duration_ns == 10**9
    sub = info.subtitles[0]
    assert (sub.id, sub.name, sub.language, sub.default) == (3, "S&S", "en", True)


def test_charlotte_layout() -> None:
    sel = _select(_track(3, "S&S"), _track(4, "Dialog - ENG"))
    assert sel.chosen.id == 4
    assert {c.id: c.kind for c in sel.candidates} == {3: "signs_songs", 4: "full"}


def test_dxd_season_layout() -> None:
    sel = _select(_track(3, "Full Subtitle (FFF/SCY)", default=True), _track(4, "Signs & Songs (FFF/SCY)"))
    assert sel.chosen.name == "Full Subtitle (FFF/SCY)"


def test_dxd_specials_two_full_prefers_default() -> None:
    sel = _select(_track(2, "Full Subtitle (CBM/IK)", default=True), _track(3, "Full Subtitle (ADZ/IK)"))
    assert sel.chosen.name == "Full Subtitle (CBM/IK)"
    assert "default" in sel.reason


def test_signs_default_does_not_win() -> None:  # D×D S00E18
    sel = _select(_track(2, "Full Subtitle (Tensai/IK)"), _track(3, "Signs & Songs (LostYears)", default=True))
    assert sel.chosen.name == "Full Subtitle (Tensai/IK)"


def test_manual_choice_from_series_toml() -> None:
    sel = _select(
        _track(2, "Full Subtitle (CBM/IK)", default=True), _track(3, "Full Subtitle (ADZ/IK)"), preferred="adz"
    )
    assert sel.chosen.id == 3 and "series.toml" in sel.reason


def test_manual_choice_without_match_warns() -> None:
    sel = _select(_track(2, "Full"), preferred="XYZ")
    assert sel.chosen.id == 2 and "XYZ" in sel.warnings[0]


def test_only_signs_is_used() -> None:
    sel = _select(_track(3, "Signs & Songs"))
    assert sel.chosen.id == 3 and "placas" in sel.reason


def test_sdh_is_never_base_and_is_reported() -> None:
    sel = _select(_track(2, "English (SDH)"), _track(3, "Full"), _track(4, "CC", hi=False), _track(5, "Eng", hi=True))
    assert sel.chosen.id == 3
    assert sel.sdh_track_ids == [2, 4, 5]


def test_only_sdh() -> None:
    with pytest.raises(NoTrack, match="só há legenda SDH"):
        _select(_track(2, "English SDH"))


def test_only_image_subtitles() -> None:
    with pytest.raises(NoTrack, match="imagem"):
        _select(_track(2, "English", codec="S_HDMV/PGS"))


def test_no_english() -> None:
    with pytest.raises(NoTrack, match="sem legenda em inglês"):
        _select(_track(2, "Español", lang="es"))


def test_und_is_candidate() -> None:
    assert _select(_track(2, "Track", lang="und")).chosen.id == 2


def test_srt_is_candidate() -> None:
    assert _select(_track(2, "English", codec="S_TEXT/UTF8")).chosen.id == 2


def test_own_track_is_ignored() -> None:
    sel = _select(_track(2, "Full"), _track(5, "Português (Brasil) — TranslaterAny", lang="pt-BR", default=True))
    assert sel.chosen.id == 2 and sel.own_track_ids == [5]


def test_foreign_ptbr_skips_unless_forced() -> None:
    subs = (_track(2, "Full"), _track(3, "Português", lang="pt-BR"))
    with pytest.raises(NoTrack, match="PT-BR de outra fonte"):
        _select(*subs)
    assert _select(*subs, force=True).chosen.id == 2
