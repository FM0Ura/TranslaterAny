"""Armazenamento em disco: caminhos, manifests, leitura de entradas e gravação de artefatos."""

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from translaterany.pipeline.manifest import Manifest, UnitInfo, load_manifest, save_manifest
from translaterany.pipeline.units import Episode, Series
from translaterany.util.fs import atomic_write, atomic_write_text


class ArtifactStore:
    """Layout:
    <data_dir>/series/<série>/{series.json, .lock, manifest.json, stages/<etapa>.*}
    <data_dir>/series/<série>/episodes/<episódio>/{manifest.json, <etapa>.*}
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def series_dir(self, series_key: str) -> Path:
        return self.data_dir / "series" / series_key

    def lock_path(self, series_key: str) -> Path:
        return self.series_dir(series_key) / ".lock"

    def artifact_dir(self, series_key: str, episode_key: str | None) -> Path:
        base = self.series_dir(series_key)
        return base / "stages" if episode_key is None else base / "episodes" / episode_key

    def manifest_path(self, series_key: str, episode_key: str | None) -> Path:
        base = self.series_dir(series_key)
        return base / "manifest.json" if episode_key is None else base / "episodes" / episode_key / "manifest.json"

    def load_manifest(self, series: Series, episode: Episode | None) -> Manifest:
        unit = UnitInfo(
            series=series.key,
            episode=episode.key if episode else None,
            source=str(episode.source) if episode else str(series.root),
        )
        return load_manifest(self.manifest_path(series.key, _key(episode)), unit)

    def save_manifest(self, series: Series, episode: Episode | None, manifest: Manifest) -> None:
        save_manifest(self.manifest_path(series.key, _key(episode)), manifest)

    def read_manifest(self, series_key: str, episode_key: str | None) -> Manifest | None:
        """Leitura só por chaves (para relatórios); None se a unidade nunca rodou."""
        path = self.manifest_path(series_key, episode_key)
        if not path.exists():
            return None
        return load_manifest(path, UnitInfo(series=series_key, episode=episode_key))

    def write_series_info(self, series: Series) -> None:
        info = {"key": series.key, "name": series.name, "root": str(series.root)}
        atomic_write_text(self.series_dir(series.key) / "series.json", json.dumps(info, ensure_ascii=False, indent=2))

    def known_series(self) -> list[dict[str, str]]:
        """Séries que já passaram por algum `run`, lidas de series.json."""
        root = self.data_dir / "series"
        if not root.exists():
            return []
        found = []
        for info in sorted(root.glob("*/series.json")):
            found.append(json.loads(info.read_text(encoding="utf-8")))
        return found

    def episode_keys(self, series_key: str) -> list[str]:
        episodes = self.series_dir(series_key) / "episodes"
        if not episodes.exists():
            return []
        return sorted(p.name for p in episodes.iterdir() if (p / "manifest.json").exists())


def _key(episode: Episode | None) -> str | None:
    return episode.key if episode is not None else None


class InputError(Exception):
    """Etapa tentou ler uma entrada não declarada ou indisponível."""


class InputReader:
    """Acesso de uma etapa aos artefatos das etapas declaradas em `inputs`."""

    def __init__(
        self,
        store: ArtifactStore,
        series: Series,
        episode: Episode | None,
        episodes: Sequence[Episode],
        allowed: Sequence[str],
        input_scopes: dict[str, str],
        manifests: ManifestSet,
    ) -> None:
        self._store = store
        self._series = series
        self._episode = episode
        self._episodes = episodes
        self._allowed = set(allowed)
        self._scopes = input_scopes
        self._manifests = manifests

    def _check(self, stage_name: str) -> None:
        if stage_name not in self._allowed:
            raise InputError(f"a etapa não declarou '{stage_name}' em inputs")

    def _artifact_path(self, stage_name: str, episode: Episode | None) -> Path:
        manifest = self._manifests.get(episode)
        record = manifest.stages.get(stage_name)
        if record is None or record.status != "done" or record.artifact is None:
            unit = episode.key if episode else self._series.key
            raise InputError(f"artefato de '{stage_name}' indisponível para {unit}")
        return self._store.artifact_dir(self._series.key, _key(episode)) / record.artifact

    def path(self, stage_name: str) -> Path:
        self._check(stage_name)
        if self._scopes[stage_name] == "series":
            return self._artifact_path(stage_name, None)
        if self._episode is None:
            raise InputError(f"'{stage_name}' é por episódio; numa etapa de série use json_all()")
        return self._artifact_path(stage_name, self._episode)

    def json[M: BaseModel](self, stage_name: str, model: type[M]) -> M:
        return model.model_validate_json(self.path(stage_name).read_text(encoding="utf-8"))

    def json_all[M: BaseModel](self, stage_name: str, model: type[M]) -> dict[str, M]:
        """Para etapas de série: artefato de cada episódio ok, indexado pela chave do episódio."""
        self._check(stage_name)
        if self._scopes[stage_name] != "episode":
            raise InputError(f"'{stage_name}' não é uma etapa por episódio")
        result: dict[str, M] = {}
        for ep in self._episodes:
            if self._manifests.get(ep).status != "ok":
                continue
            path = self._artifact_path(stage_name, ep)
            result[ep.key] = model.model_validate_json(path.read_text(encoding="utf-8"))
        return result


class OutputWriter:
    """Gravação do (único) artefato de uma etapa. O nome do arquivo é o nome da etapa."""

    def __init__(self, directory: Path, stage_name: str) -> None:
        self._directory = directory
        self._stage_name = stage_name
        self.written: str | None = None

    def _claim(self, filename: str) -> Path:
        if self.written is not None:
            raise RuntimeError(f"a etapa '{self._stage_name}' tentou gravar mais de um artefato")
        self.written = filename
        return self._directory / filename

    def json(self, model: BaseModel) -> None:
        path = self._claim(f"{self._stage_name}.json")
        atomic_write_text(path, model.model_dump_json(indent=2))

    def file(self, suffix: str, data: bytes) -> None:
        if not suffix.startswith("."):
            raise ValueError("suffix deve começar com '.', ex.: '.ass'")
        path = self._claim(f"{self._stage_name}{suffix}")
        atomic_write(path, data)

    @property
    def path(self) -> Path | None:
        return self._directory / self.written if self.written else None


class ManifestSet:
    """Manifests carregados de uma série (série + episódios), mantidos em memória durante a execução."""

    def __init__(self, store: ArtifactStore, series: Series, episodes: Sequence[Episode]) -> None:
        self._store = store
        self._series = series
        self.series = store.load_manifest(series, None)
        self.episodes = {ep.key: store.load_manifest(series, ep) for ep in episodes}

    def get(self, episode: Episode | None) -> Manifest:
        return self.series if episode is None else self.episodes[episode.key]

    def save(self, episode: Episode | None) -> None:
        self._store.save_manifest(self._series, episode, self.get(episode))
