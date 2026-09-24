"""Unidades de trabalho: série e episódio."""

from dataclasses import dataclass
from pathlib import Path

from translaterany.util.fs import slugify


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    root: Path


@dataclass(frozen=True)
class Episode:
    series: Series
    key: str
    source: Path


def discover(path: Path) -> tuple[Series, list[Episode]]:
    """Descoberta PROVISÓRIA do M0: a pasta é a série; episódios são todos os *.mkv sob ela.

    Substituída no M1 pela varredura real (SxxEyy, biblioteca inteira).
    """
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"não é uma pasta: {path}")
    series = Series(key=slugify(root.name), name=root.name, root=root)
    sources = sorted(p for p in root.rglob("*.mkv") if p.is_file())
    episodes = [
        Episode(series=series, key=slugify(str(src.relative_to(root).with_suffix(""))), source=src) for src in sources
    ]
    return series, episodes
