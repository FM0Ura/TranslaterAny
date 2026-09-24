"""Fixtures compartilhadas pelos testes."""

from pathlib import Path

import pytest


@pytest.fixture
def series_dir(tmp_path: Path) -> Path:
    """Série fictícia com 3 'episódios' (arquivos .mkv de texto)."""
    root = tmp_path / "library" / "Minha Série (2020)"
    (root / "Season 1").mkdir(parents=True)
    for i in (1, 2, 3):
        (root / "Season 1" / f"S01E0{i}.mkv").write_text(f"episodio {i}", encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"
