"""Fixtures compartilhadas pelos testes."""

from pathlib import Path

import pytest
from fake_stages import TEST_STAGES

from translaterany.pipeline.registry import REGISTRY, StageRegistry

for _cls in TEST_STAGES:  # disponíveis também no REGISTRY global (usado pela CLI)
    if _cls.name not in REGISTRY:
        REGISTRY.register(_cls)


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    for cls in TEST_STAGES:
        cls.calls = []


@pytest.fixture
def registry() -> StageRegistry:
    reg = StageRegistry()
    for cls in TEST_STAGES:
        reg.register(cls)
    return reg


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
