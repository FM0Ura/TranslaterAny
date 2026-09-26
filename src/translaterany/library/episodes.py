"""Identificação de episódios pelo nome do arquivo (padrão Sonarr: S01E04, S01E01-02)."""

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"(?<![a-z0-9])s(\d{1,2})e(\d{1,3})(?:-(\d{1,3}))?(?![0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class EpisodeId:
    season: int
    first: int
    last: int | None = None  # episódio múltiplo: S01E01-02

    @property
    def key(self) -> str:
        key = f"S{self.season:02d}E{self.first:02d}"
        return f"{key}-{self.last:02d}" if self.last is not None else key


def parse_episode(filename: str) -> EpisodeId | None:
    """Primeira ocorrência de SxxEyy (ou SxxEyy-zz) no nome; None se não houver."""
    match = _PATTERN.search(filename)
    if match is None:
        return None
    last = int(match.group(3)) if match.group(3) else None
    return EpisodeId(season=int(match.group(1)), first=int(match.group(2)), last=last)
