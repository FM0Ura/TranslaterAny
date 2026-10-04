"""Interface de etapa. Toda etapa do pipeline implementa `Stage`."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.llm.client import LLMClient
from translaterany.pipeline.artifacts import ArtifactStore, InputReader, OutputWriter
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.pipeline.units import Episode, Series
from translaterany.util.doctor import Check

if TYPE_CHECKING:
    from translaterany.config.model import AppConfig


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
    previous_output: Path | None = None  # artefato anterior desta etapa para a unidade, se houver
    force: bool = False  # `run --force`: permite sobrescrever PT-BR de terceiros
    store: ArtifactStore | None = None
    metrics: StageMetrics = field(default_factory=StageMetrics)
    source_language: Any = None  # LanguageInfo
    target_language: Any = None  # LanguageInfo
    target_profile: Any = None  # LanguageProfile


class Stage(ABC):
    name: ClassVar[str]
    version: ClassVar[str]  # mudar invalida o cache (lógica ou prompt mudou)
    scope: ClassVar[StageScope]
    inputs: tuple[str, ...] = ()  # pode ser redefinido por instância (a partir das opções)
    reads_source: ClassVar[bool] = False  # lê o arquivo de origem diretamente
    translates: ClassVar[bool] = False  # produz texto traduzido (libera publish/remux)
    produces_texts: ClassVar[bool] = False  # artefato é UnitTexts (instantâneo medido pela quality_checks)
    produces_dialogue: ClassVar[bool] = False  # artefato é o mapa de diálogo por frase (entrada da redistribuição)
    enabled_by_default: ClassVar[bool] = True  # sem [stages.X] no config, a etapa roda?
    Options: ClassVar[type[BaseModel]] = NoOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        self.options = options if options is not None else self.Options()

    @abstractmethod
    def run(self, ctx: StageContext) -> None:
        """Lê entradas via ctx.inputs e grava exatamente um artefato via ctx.output."""

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        """Dados extras (JSON) que entram na chave de cache — ex.: a parte do series.toml que a etapa usa."""
        return None

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:  # noqa: B027
        """Chamado pelo loader com as etapas habilitadas que vêm antes desta e o config.
        Etapas que dependem da composição do pipeline (ex.: quality_checks) ajustam `inputs` aqui."""

    def verify_cached(self, ctx: StageContext, artifact_path: Path) -> bool:
        """Chamado num cache hit. Etapas com efeitos fora do diretório de dados conferem se eles
        ainda estão como registrados; False força a reexecução."""
        return True

    def doctor_checks(self, cfg: Any = None) -> list[Check]:
        return []
