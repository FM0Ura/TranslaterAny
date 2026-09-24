"""Funções de apoio para rodar etapas reais sobre MKVs sintéticos."""

from pathlib import Path

from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage


def run_stages(data_dir: Path, root: Path, stages: list[Stage], force: bool = False):
    store = ArtifactStore(data_dir)
    series, episodes = discover(root)
    summary = Runner(stages, store, FakeLLM()).run(series, episodes, force=force)
    return summary, store, series, episodes


def artifact(store: ArtifactStore, series, episode, name: str) -> Path:
    return store.artifact_dir(series.key, episode.key) / name
