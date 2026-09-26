"""Unidades de trabalho: série e episódio."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

LINE_TYPES = ("dialogue", "sign", "song", "romaji", "karaoke", "drawing", "comment")


class SeriesMetadataConfig(BaseModel):
    """Configurações da seção [metadata] do series.toml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anilist_id: int | None = None


class SeriesConfig(BaseModel):
    """Conteúdo validado do `series.toml` opcional da pasta da série."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    track: str | None = None  # parte do nome da faixa preferida
    styles: dict[str, str] = Field(default_factory=dict)  # estilo -> tipo de linha
    metadata: SeriesMetadataConfig = Field(default_factory=SeriesMetadataConfig)


@dataclass(frozen=True)
class Series:
    key: str = ""
    name: str = ""
    root: Path = field(default_factory=lambda: Path("."))
    config: SeriesConfig = field(default_factory=SeriesConfig, compare=False)
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.path is not None and self.root == Path("."):
            object.__setattr__(self, "root", Path(self.path))
        elif self.root != Path(".") and self.path is None:
            object.__setattr__(self, "path", Path(self.root))
        elif self.path is None and self.root == Path("."):
            object.__setattr__(self, "path", Path(self.root))
        elif self.path is not None:
            object.__setattr__(self, "root", Path(self.path))
            object.__setattr__(self, "path", Path(self.path))
        if not self.key and self.name:
            import re

            slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", self.name.lower()).strip("-")
            object.__setattr__(self, "key", slug or "series")


@dataclass(frozen=True)
class Episode:
    series: Series
    key: str
    source: Path
