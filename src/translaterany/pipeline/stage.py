"""Interface de etapa. Toda etapa do pipeline implementa `Stage`."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.llm.client import LLMClient
from translaterany.pipeline.artifacts import InputReader, OutputWriter
from translaterany.pipeline.units import Episode, Series
from translaterany.util.doctor import Check


class StageScope(StrEnum):
    EPISODE = "episode"
    SERIES = "series"


class NoOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkipEpisode(Exception):  # noqa: N818 — é um sinal, não um erro
    """Lançada por uma etapa para pular o episódio (ex.: legenda em imagem)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class StageContext:
    series: Series
    episode: Episode | None  # None quando a etapa é de escopo série
    episodes: Sequence[Episode]  # todos os episódios da série
    inputs: InputReader
    output: OutputWriter
    llm: LLMClient
    log: logging.Logger


class Stage(ABC):
    name: ClassVar[str]
    version: ClassVar[str]  # mudar invalida o cache (lógica ou prompt mudou)
    scope: ClassVar[StageScope]
    inputs: ClassVar[tuple[str, ...]] = ()
    reads_source: ClassVar[bool] = False  # lê o arquivo de origem diretamente
    Options: ClassVar[type[BaseModel]] = NoOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        self.options = options if options is not None else self.Options()

    @abstractmethod
    def run(self, ctx: StageContext) -> None:
        """Lê entradas via ctx.inputs e grava exatamente um artefato via ctx.output."""

    def doctor_checks(self) -> list[Check]:
        return []
