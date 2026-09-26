import os
import time
from pathlib import Path

import pytest

from translaterany.library import (
    SeriesConfigError,
    discover,
    is_series_dir,
    load_series_config,
    parse_episode,
    scan_library,
    scan_series,
)


def _touch(path: Path, text: str = "x", age: float = 3600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    old = time.time() - age
    os.utime(path, (old, old))
    return path


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("S01E04 - Moment of Earnest Bluray-1080p.mkv", "S01E04"),
        ("Show - s1e2.mkv", "S01E02"),
        ("S00E02 - Special.mkv", "S00E02"),
        ("S01E01-02 - Double.mkv", "S01E01-02"),
        ("S02E100 - Long.mkv", "S02E100"),
    ],
)
def test_parse_episode(name: str, key: str) -> None:
    episode = parse_episode(name)
    assert episode is not None and episode.key == key


def test_parse_episode_without_pattern() -> None:
    assert parse_episode("Movie (2020).mkv") is None
    assert parse_episode("HS01E01X.mkv") is None  # colado a letras não conta


def test_scan_series_keys_order_and_case(tmp_path: Path) -> None:
    root = tmp_path / "Minha Série (2020)"
    _touch(root / "Season 1" / "S01E02 - B.mkv")
    _touch(root / "Season 1" / "S01E01 - A.MKV")
    _touch(root / "Specials" / "S00E01 - Sp.mkv")
    _touch(root / "Season 1" / "S01E01 - A.nfo")
    scan = scan_series(root)
    assert [e.key for e in scan.episodes] == ["S00E01", "S01E01", "S01E02"]
    assert scan.episodes[1].source.name == "S01E01 - A.MKV"
    assert scan.ignored == [] and scan.warnings == []


def test_hidden_files_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01.mkv")
    _touch(root / ".S01E01.translaterany-tmp.mkv")
    assert [e.key for e in scan_series(root).episodes] == ["S01E01"]


def test_duplicates_are_ignored_with_reason(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01 - A HDTV.mkv")
    _touch(root / "S01E01 - A Bluray.mkv")
    _touch(root / "S01E02.mkv")
    scan = scan_series(root)
    assert [e.key for e in scan.episodes] == ["S01E02"]
    assert len(scan.ignored) == 2 and "duplicado" in scan.ignored[0].reason


def test_recent_files_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01.mkv")
    _touch(root / "S01E02.mkv", age=5)
    scan = scan_series(root, min_file_age=120)
    assert [e.key for e in scan.episodes] == ["S01E01"]
    assert "download" in scan.ignored[0].reason


def test_file_without_pattern_gets_slug_key_and_warning(tmp_path: Path) -> None:
    root = tmp_path / "Filme"
    _touch(root / "Filme (2020).mkv")
    scan = scan_series(root)
    assert scan.episodes[0].key.startswith("filme-2020-")
    assert "sem SxxEyy" in scan.warnings[0]


def test_identity_from_nfo_is_stable_across_moves(tmp_path: Path) -> None:
    nfo = "<tvshow><title>X</title><tvdbid>289679</tvdbid><tmdbid>63145</tmdbid></tvshow>"
    for place in ("a", "b"):
        _touch(tmp_path / place / "Charlotte (2015)" / "tvshow.nfo", nfo)
    key_a = scan_series(tmp_path / "a" / "Charlotte (2015)").series.key
    key_b = scan_series(tmp_path / "b" / "Charlotte (2015)").series.key
    assert key_a == key_b and key_a.startswith("charlotte-2015-")


def test_identity_without_nfo_depends_on_path(tmp_path: Path) -> None:
    for place in ("a", "b"):
        _touch(tmp_path / place / "Serie" / "S01E01.mkv")
    assert scan_series(tmp_path / "a" / "Serie").series.key != scan_series(tmp_path / "b" / "Serie").series.key


def test_broken_nfo_falls_back_to_path(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "tvshow.nfo", "<tvshow><tvdbid>1</tvdb")
    _touch(root / "S01E01.mkv")
    assert scan_series(root).series.key.startswith("serie-")


def test_unicode_series_name(tmp_path: Path) -> None:
    root = tmp_path / "High School D×D (2012)"
    _touch(root / "Specials" / "S00E14 - Levia and So ☆.mkv")
    scan = scan_series(root)
    assert scan.series.key.startswith("high-school-d-d-2012-")
    assert scan.episodes[0].source.name == "S00E14 - Levia and So ☆.mkv"


def test_series_or_library_detection(tmp_path: Path) -> None:
    lib = tmp_path / "Anime"
    _touch(lib / "Serie A" / "Season 1" / "S01E01.mkv")
    _touch(lib / "Serie B" / "tvshow.nfo", "<tvshow/>")
    _touch(lib / "Serie B" / "S01E01.mkv")
    (lib / "Vazia").mkdir()
    assert not is_series_dir(lib)
    assert [s.series.name for s in scan_library(lib)] == ["Serie A", "Serie B"]
    assert [s.series.name for s in scan_library(lib / "Serie A")] == ["Serie A"]


def test_scan_rejects_file(tmp_path: Path) -> None:
    f = _touch(tmp_path / "S01E01.mkv")
    with pytest.raises(NotADirectoryError):
        scan_library(f)


def test_discover_shortcut(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01.mkv", age=0)  # o atalho não filtra por idade
    series, episodes = discover(root)
    assert series.name == "Serie" and [e.key for e in episodes] == ["S01E01"]


def test_series_config_valid(tmp_path: Path) -> None:
    _touch(tmp_path / "series.toml", '[subtitles]\ntrack = "ADZ"\n[styles]\n"Mirror" = "sign"\n')
    config = load_series_config(tmp_path)
    assert config.track == "ADZ" and config.styles == {"Mirror": "sign"}
    assert scan_series(tmp_path).series.config.track == "ADZ"


def test_series_config_absent(tmp_path: Path) -> None:
    config = load_series_config(tmp_path)
    assert config.track is None and config.styles == {}


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("[subtitles\n", "arquivo inválido"),
        ("[metadata]\nx = 1\n", "seção desconhecida"),
        ('[subtitles]\nlang = "en"\n', "apenas 'track'"),
        ('[styles]\n"Mirror" = "placa"\n', "use um de"),
    ],
)
def test_series_config_invalid(tmp_path: Path, text: str, match: str) -> None:
    _touch(tmp_path / "series.toml", text)
    with pytest.raises(SeriesConfigError, match=match):
        load_series_config(tmp_path)


def test_scan_series_reports_broken_series_toml(tmp_path: Path) -> None:
    _touch(tmp_path / "Serie" / "S01E01.mkv")
    _touch(tmp_path / "Serie" / "series.toml", "[subtitles\n")
    scan = scan_series(tmp_path / "Serie")
    assert scan.episodes == [] and scan.error is not None and "series.toml" in scan.error


def test_season_folder_belongs_to_parent_series(tmp_path: Path) -> None:
    root = tmp_path / "Charlotte (2015)"
    _touch(root / "tvshow.nfo", "<tvshow><tvdbid>289679</tvdbid></tvshow>")
    _touch(root / "Season 1" / "S01E01.mkv")
    _touch(root / "Specials" / "S00E02.mkv")
    scans = scan_library(root / "Season 1")
    assert [s.series.name for s in scans] == ["Charlotte (2015)"]
    assert [e.key for e in scans[0].episodes] == ["S01E01"]
    assert scans[0].series.key == scan_series(root).series.key
