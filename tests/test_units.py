from pathlib import Path

import pytest

from translaterany.pipeline.units import discover


def test_discover_finds_mkv_recursively_sorted(series_dir: Path) -> None:
    (series_dir / "Specials").mkdir()
    (series_dir / "Specials" / "S00E01.mkv").write_text("x")
    (series_dir / "Season 1" / "notes.nfo").write_text("x")
    series, episodes = discover(series_dir)
    assert series.name == "Minha Série (2020)"
    assert series.root == series_dir.resolve()
    assert [e.source.name for e in episodes] == ["S01E01.mkv", "S01E02.mkv", "S01E03.mkv", "S00E01.mkv"]
    assert len({e.key for e in episodes}) == 4


def test_discover_keys_are_stable(series_dir: Path) -> None:
    assert [e.key for e in discover(series_dir)[1]] == [e.key for e in discover(series_dir)[1]]


def test_discover_unicode_folder(tmp_path: Path) -> None:
    root = tmp_path / "High School D×D (2012)"
    root.mkdir()
    (root / "S00E14 - Levia and So ☆.mkv").write_text("x")
    series, episodes = discover(root)
    assert series.key.startswith("high-school-d-d-2012-")
    assert episodes[0].source.name == "S00E14 - Levia and So ☆.mkv"


def test_discover_rejects_file(tmp_path: Path) -> None:
    f = tmp_path / "a.mkv"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        discover(f)


def test_discover_empty_folder(tmp_path: Path) -> None:
    series, episodes = discover(tmp_path)
    assert episodes == []
