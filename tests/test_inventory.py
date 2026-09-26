import json
from pathlib import Path

from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.stages.inventory import InventoryStage


def test_inventory_records_size_and_fingerprint(data_dir: Path, series_dir: Path) -> None:
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    Runner([InventoryStage()], store, FakeLLM()).run(series, episodes)
    art = json.loads((store.artifact_dir(series.key, episodes[0].key) / "inventory.json").read_text())
    assert art["size"] == len("episodio 1")
    assert art["fingerprint"].startswith("sha256:")
    assert art["source"] == str(episodes[0].source)


def test_inventory_reruns_only_when_file_changes(data_dir: Path, series_dir: Path) -> None:
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    Runner([InventoryStage()], store, FakeLLM()).run(series, episodes)
    (series_dir / "Season 1" / "S01E01.mkv").write_bytes(b"x" * 3_000_000)
    summary = Runner([InventoryStage()], store, FakeLLM()).run(series, episodes)
    assert summary.stages["inventory"].done == 1 and summary.stages["inventory"].cached == 2


def test_builtin_stages_registered_and_default_pipeline() -> None:
    from translaterany.stages import DEFAULT_PIPELINE

    assert "inventory" in REGISTRY
    assert DEFAULT_PIPELINE == (
        "inventory",
        "select_track",
        "extract",
        "normalize",
        "classify",
        "translate_dialogue",
        "write",
        "publish",
        "remux",
    )
    assert REGISTRY.get("remux").enabled_by_default is False
