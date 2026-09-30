from datetime import UTC, datetime
from pathlib import Path

import pytest

from translaterany.pipeline.manifest import (
    Manifest,
    ManifestError,
    StageRecord,
    UnitInfo,
    load_manifest,
    save_manifest,
)


def _record() -> StageRecord:
    now = datetime.now(UTC)
    return StageRecord(
        status="done", key="k", artifact="a.json", artifact_hash="h", started_at=now, finished_at=now, duration_s=0.1
    )


def test_missing_manifest_returns_empty(tmp_path: Path) -> None:
    manifest = load_manifest(tmp_path / "manifest.json", UnitInfo(series="s", episode="e"))
    assert manifest.status == "ok" and manifest.stages == {}
    assert manifest.unit.episode == "e"


def test_roundtrip_uses_schema_key(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    manifest = Manifest(unit=UnitInfo(series="s"))
    manifest.stages["x"] = _record()
    save_manifest(path, manifest)
    assert '"schema": 2' in path.read_text()
    loaded = load_manifest(path, UnitInfo(series="ignorado"))
    assert loaded.unit.series == "s"
    assert loaded.stages["x"].artifact == "a.json"


def test_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"schema": 99, "unit": {"series": "s"}}')
    with pytest.raises(ManifestError, match="schema 99"):
        load_manifest(path, UnitInfo(series="s"))


def test_corrupted_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{não é json")
    with pytest.raises(ManifestError):
        load_manifest(path, UnitInfo(series="s"))


def test_non_utf8_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes('{"schema": 1, "unit": {"series": "s"}, "skip_reason": "episódio"}'.encode("latin-1"))
    with pytest.raises(ManifestError):
        load_manifest(path, UnitInfo(series="s"))


def test_unreadable_manifest_path(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.mkdir()
    with pytest.raises(ManifestError):
        load_manifest(path, UnitInfo(series="s"))
