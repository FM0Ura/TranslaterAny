"""Descoberta de séries e episódios numa pasta (uma série ou uma biblioteca)."""

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from translaterany.library.episodes import parse_episode
from translaterany.library.nfo import series_identity
from translaterany.library.series_config import SeriesConfigError, load_series_config
from translaterany.pipeline.units import Episode, Series
from translaterany.util.fs import slug_base, slugify

_SEASON_DIR = re.compile(r"^(season\s*\d+|specials)$", re.IGNORECASE)


@dataclass(frozen=True)
class Ignored:
    path: Path
    reason: str


@dataclass
class SeriesScan:
    series: Series
    episodes: list[Episode]
    ignored: list[Ignored] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None  # series.toml inválido: a série não é processada


def is_series_dir(path: Path) -> bool:
    if (path / "tvshow.nfo").is_file():
        return True
    for child in path.iterdir():
        if child.is_dir() and _SEASON_DIR.match(child.name):
            return True
        if child.is_file() and _is_video(child):
            return True
    return False


def scan_library(path: Path, *, min_file_age: float = 0.0, now: float | None = None) -> list[SeriesScan]:
    """A pasta é uma série, ou uma biblioteca cujas subpastas (um nível) são séries."""
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"não é uma pasta: {path}")
    if _SEASON_DIR.match(root.name) and is_series_dir(root.parent):  # pasta de temporada: série = pasta-mãe
        return [scan_series(root.parent, min_file_age=min_file_age, now=now, only=root)]
    if is_series_dir(root):
        return [scan_series(root, min_file_age=min_file_age, now=now)]
    children = sorted(c for c in root.iterdir() if c.is_dir() and not c.name.startswith(".") and is_series_dir(c))
    return [scan_series(c, min_file_age=min_file_age, now=now) for c in children]


def scan_series(
    path: Path, *, min_file_age: float = 0.0, now: float | None = None, only: Path | None = None
) -> SeriesScan:
    """Lê o series.toml e lista os episódios. series.toml inválido vira `error` (a série não roda)."""
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"não é uma pasta: {path}")
    identity = series_identity(root) or f"path:{root}"
    key = f"{slug_base(root.name)}-{hashlib.sha256(identity.encode()).hexdigest()[:6]}"
    try:
        config = load_series_config(root)
    except SeriesConfigError as exc:
        return SeriesScan(series=Series(key=key, name=root.name, root=root), episodes=[], error=str(exc))
    series = Series(key=key, name=root.name, root=root, config=config)
    scan = SeriesScan(series=series, episodes=[])
    current = time.time() if now is None else now

    by_key: dict[str, list[Path]] = defaultdict(list)
    base = only.resolve() if only is not None else root
    for video in sorted(p for p in base.rglob("*") if p.is_file() and _is_video(p)):
        if any(part.startswith(".") for part in video.relative_to(root).parts):
            continue  # ocultos (inclui temporários da própria app)
        if current - video.stat().st_mtime < min_file_age:
            scan.ignored.append(Ignored(video, "modificado há pouco (possível download em andamento)"))
            continue
        episode_id = parse_episode(video.name)
        if episode_id is None:
            scan.warnings.append(f"sem SxxEyy no nome: {video.name}")
            by_key[slugify(video.stem)].append(video)
        else:
            by_key[episode_id.key].append(video)

    for ep_key, videos in by_key.items():
        if len(videos) > 1:
            names = " e ".join(v.name for v in videos)
            scan.ignored.extend(Ignored(v, f"episódio duplicado ({ep_key}): {names}") for v in videos)
            continue
        scan.episodes.append(Episode(series=series, key=ep_key, source=videos[0]))
    scan.episodes.sort(key=lambda e: e.key)
    return scan


def discover(path: Path) -> tuple[Series, list[Episode]]:
    """Atalho para uma única série, sem filtro de idade (usado por retry/status e nos testes).
    Uma pasta `Season N`/`Specials` resolve para a série-mãe, como no `run`."""
    root = path.resolve()
    if root.is_dir() and _SEASON_DIR.match(root.name) and is_series_dir(root.parent):
        scan = scan_series(root.parent, only=root)
    else:
        scan = scan_series(path)
    return scan.series, scan.episodes


def _is_video(path: Path) -> bool:
    return path.suffix.lower() == ".mkv"
