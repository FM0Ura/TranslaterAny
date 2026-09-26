"""Unidades de trabalho: série e episódio."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

LINE_TYPES = ("dialogue", "sign", "song", "romaji", "karaoke", "drawing", "comment")


class SeriesConfig(BaseModel):
    """Conteúdo validado do `series.toml` opcional da pasta da série."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    track: str | None = None  # parte do nome da faixa preferida
    styles: dict[str, str] = Field(default_factory=dict)  # estilo -> tipo de linha


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    root: Path
    config: SeriesConfig = field(default_factory=SeriesConfig, compare=False)


@dataclass(frozen=True)
class Episode:
    series: Series
    key: str
    source: Path
