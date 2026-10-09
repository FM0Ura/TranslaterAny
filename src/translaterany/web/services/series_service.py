"""Serviço para descoberta, metadados e status de séries e episódios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from translaterany.config.loader import default_data_dir


class EpisodeSummary(BaseModel):
    key: str
    title: str | None = None
    status: str = "pending"  # "pending", "running", "completed", "failed"
    current_stage: str | None = None
    progress_percent: float = 0.0
    subtitles_available: bool = False
    subtitles_path: str | None = None


class SeriesSummary(BaseModel):
    key: str
    title: str
    poster_url: str | None = None
    backdrop_url: str | None = None
    total_episodes: int = 0
    completed_episodes: int = 0
    status: str = "pending"  # "pending", "in_progress", "completed"


class SeriesDetail(BaseModel):
    key: str
    title: str
    poster_url: str | None = None
    backdrop_url: str | None = None
    synopsis: str | None = None
    total_episodes: int = 0
    completed_episodes: int = 0
    status: str = "pending"
    episodes: list[EpisodeSummary] = []


class SeriesService:
    """Gerencia a visualização e listagem das séries no banco de dados / artefatos."""

    def __init__(self, data_dir: Path | None = None, library_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.library_dir = Path(library_dir) if library_dir is not None else None

    def _get_series_dirs(self) -> list[Path]:
        series_root = self.data_dir / "series"
        if not series_root.is_dir():
            return []
        return sorted([p for p in series_root.iterdir() if p.is_dir() and not p.name.startswith(".")])

    def list_series(self) -> list[SeriesSummary]:
        result: list[SeriesSummary] = []
        for sdir in self._get_series_dirs():
            detail = self._read_series_dir(sdir)
            result.append(
                SeriesSummary(
                    key=detail.key,
                    title=detail.title,
                    poster_url=detail.poster_url,
                    backdrop_url=detail.backdrop_url,
                    total_episodes=detail.total_episodes,
                    completed_episodes=detail.completed_episodes,
                    status=detail.status,
                )
            )
        return result

    def get_series(self, key: str) -> SeriesDetail | None:
        for sdir in self._get_series_dirs():
            if sdir.name == key or sdir.name.startswith(f"{key}-") or key.startswith(f"{sdir.name}-"):
                return self._read_series_dir(sdir)
        return None

    def get_episode_subtitles(self, series_key: str, episode_key: str) -> str | None:
        series_detail = self.get_series(series_key)
        if not series_detail:
            return None
        series_dir = self.data_dir / "series" / series_detail.key
        ep_dir = series_dir / "episodes" / episode_key
        if not ep_dir.is_dir():
            return None

        # Procura arquivos ass / srt produzidos
        for candidate in ["publish.pt-BR.ass", "publish.ass", "write.ass", "write.pt-BR.ass"]:
            p = ep_dir / candidate
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace")

        # Procura qualquer .ass gerado
        for p in ep_dir.glob("*.ass"):
            return p.read_text(encoding="utf-8", errors="replace")
        return None

    def get_qa_report(self, series_key: str, episode_key: str) -> dict[str, Any] | None:
        series_detail = self.get_series(series_key)
        if not series_detail:
            return None
        series_dir = self.data_dir / "series" / series_detail.key
        ep_dir = series_dir / "episodes" / episode_key
        if not ep_dir.is_dir():
            return None

        for candidate in ["quality_checks.json", "qa_loop.json"]:
            p = ep_dir / candidate
            if p.is_file():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return None

    def _read_series_dir(self, sdir: Path) -> SeriesDetail:
        key = sdir.name
        title = key.replace("-", " ").title()
        poster_url: str | None = None
        backdrop_url: str | None = None
        synopsis: str | None = None

        # Tenta ler metadados em json se houver
        metadata_file = sdir / "metadata.json"
        if not metadata_file.is_file():
            metadata_file = sdir / "stages" / "metadata.json"

        if metadata_file.is_file():
            try:
                mdata = json.loads(metadata_file.read_text(encoding="utf-8"))
                if isinstance(mdata, dict):
                    title = mdata.get("title") or mdata.get("series_title") or title
                    poster_url = mdata.get("poster_url")
                    backdrop_url = mdata.get("backdrop_url")
                    synopsis = mdata.get("synopsis") or mdata.get("description")
            except Exception:
                pass

        # Tenta sinopse no story.yaml
        story_file = sdir / "story.yaml"
        if not synopsis and story_file.is_file():
            try:
                import ruamel.yaml

                yaml = ruamel.yaml.YAML(typ="safe")
                sdata = yaml.load(story_file.read_text(encoding="utf-8"))
                if isinstance(sdata, dict) and "synopsis" in sdata:
                    synopsis = sdata["synopsis"]
            except Exception:
                pass

        # Lê episódios
        episodes: list[EpisodeSummary] = []
        episodes_dir = sdir / "episodes"
        if episodes_dir.is_dir():
            for ep_sub in sorted(episodes_dir.iterdir()):
                if ep_sub.is_dir() and not ep_sub.name.startswith("."):
                    ep_summary = self._read_episode_dir(ep_sub)
                    episodes.append(ep_summary)

        completed_count = sum(1 for ep in episodes if ep.status == "completed")
        total_count = len(episodes)
        status = "completed" if (total_count > 0 and completed_count == total_count) else (
            "in_progress" if completed_count > 0 else "pending"
        )

        return SeriesDetail(
            key=key,
            title=title,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            synopsis=synopsis,
            total_episodes=total_count,
            completed_episodes=completed_count,
            status=status,
            episodes=episodes,
        )

    def _read_episode_dir(self, ep_dir: Path) -> EpisodeSummary:
        ep_key = ep_dir.name
        manifest_file = ep_dir / "manifest.json"
        status = "pending"
        current_stage: str | None = None
        progress = 0.0
        subtitles_available = False
        subtitles_path: str | None = None

        if manifest_file.is_file():
            try:
                mdata = json.loads(manifest_file.read_text(encoding="utf-8"))
                stages = mdata.get("stages", {})
                if isinstance(stages, dict):
                    completed_stages = [
                        st_name for st_name, st_info in stages.items()
                        if isinstance(st_info, dict) and st_info.get("status") == "completed"
                    ]
                    # Se publish ou write concluiu
                    if "publish" in completed_stages or "write" in completed_stages:
                        status = "completed"
                        progress = 100.0
                    elif completed_stages:
                        status = "running"
                        current_stage = completed_stages[-1]
                        progress = min(95.0, (len(completed_stages) / 28.0) * 100.0)
            except Exception:
                pass

        for cand in ["publish.pt-BR.ass", "publish.ass", "write.ass", "write.pt-BR.ass"]:
            if (ep_dir / cand).is_file():
                subtitles_available = True
                subtitles_path = str(ep_dir / cand)
                break

        return EpisodeSummary(
            key=ep_key,
            title=None,
            status=status,
            current_stage=current_stage,
            progress_percent=progress,
            subtitles_available=subtitles_available,
            subtitles_path=subtitles_path,
        )
