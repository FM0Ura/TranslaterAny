"""Etapa metadata: consulta AniList e Jikan para obter metadados da série."""

import logging
import re
from typing import Any

from pydantic import BaseModel

from translaterany.config.loader import default_data_dir
from translaterany.memory.anilist import AniListClient
from translaterany.memory.artifacts import MetadataArtifact
from translaterany.memory.jikan import JikanClient
from translaterany.memory.models import EpisodeSynopsis, StoryMemory
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series

logger = logging.getLogger(__name__)

_UNSET = object()


@register_stage
class MetadataStage(Stage):
    """Etapa de série que busca metadados externos (AniList, Jikan) e gera metadata.json."""

    name = "metadata"
    version = "1"
    scope = StageScope.SERIES
    inputs = ("inventory",)
    translates = False

    def __init__(
        self,
        options: BaseModel | None = None,
        anilist_client: Any = _UNSET,
        jikan_client: Any = _UNSET,
    ) -> None:
        if isinstance(options, BaseModel):
            super().__init__(options)
        else:
            super().__init__(None)
            if anilist_client is _UNSET and options is not None:
                anilist_client = options

        if anilist_client is _UNSET:
            self.anilist_client: Any = AniListClient(default_data_dir() / "cache")
        else:
            self.anilist_client = anilist_client

        if jikan_client is _UNSET:
            self.jikan_client: Any = JikanClient(default_data_dir() / "cache")
        else:
            self.jikan_client = jikan_client

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        metadata_cfg = getattr(getattr(series, "config", None), "metadata", None)
        return {"anilist_id": getattr(metadata_cfg, "anilist_id", None)}

    def run(self, ctx: StageContext) -> None:
        raw_name = ctx.series.name.strip()
        match_re = re.match(r"^(.*?)(?:\s*\((\d{4})\))?$", raw_name)
        if match_re:
            title = match_re.group(1).strip()
            year = int(match_re.group(2)) if match_re.group(2) else None
        else:
            title = raw_name
            year = None

        metadata_cfg = getattr(getattr(ctx.series, "config", None), "metadata", None)
        override_id: int | None = getattr(metadata_cfg, "anilist_id", None)

        match = None
        if override_id is not None and hasattr(self.anilist_client, "get_anime_by_id"):
            try:
                match = self.anilist_client.get_anime_by_id(override_id)
            except Exception as exc:
                logger.warning("Falha ao buscar AniList por ID %s: %s", override_id, exc)

        if match is None and self.anilist_client is not None:
            try:
                match = self.anilist_client.search_anime(title, year)
            except Exception as exc:
                logger.warning("Falha ao buscar AniList para '%s' (%s): %s", title, year, exc)

        if match is not None:
            synopses: dict[int, EpisodeSynopsis] = {}
            if self.jikan_client is not None and match.mal_id is not None:
                try:
                    synopses = self.jikan_client.get_episode_synopses(match.mal_id) or {}
                except Exception as exc:
                    logger.warning("Falha ao obter sinopses do Jikan para mal_id=%s: %s", match.mal_id, exc)
                    synopses = {}

            episodes_map = {
                (syn.episode_key if getattr(syn, "episode_key", None) else f"EP{num}"): syn
                for num, syn in synopses.items()
            }
            story = StoryMemory(
                title=match.title,
                romaji_title=match.romaji,
                year=match.year,
                genres=match.genres,
                episodes=episodes_map,
            )
            artifact = MetadataArtifact(
                matched=True,
                anilist_id=override_id if override_id is not None else match.anilist_id,
                mal_id=match.mal_id,
                title=match.title,
                characters=match.characters,
                story=story,
            )
        else:
            artifact = MetadataArtifact(
                matched=False,
                anilist_id=override_id,
                title=title,
            )

        ctx.output.json(artifact)


__all__ = ["MetadataStage"]
