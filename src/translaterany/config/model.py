"""Formato do arquivo de configuração (config.toml)."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneralConfig(_Strict):
    data_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class DiscoveryConfig(_Strict):
    min_file_age: float = 120  # segundos; arquivos mais novos são ignorados (download em andamento)


class PipelineConfig(_Strict):
    stages: list[str]


class StageConfig(_Strict):
    enabled: bool | None = None  # None: usa o padrão da etapa (enabled_by_default)
    options: dict[str, Any] = Field(default_factory=dict)


class AppConfig(_Strict):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    pipeline: PipelineConfig | None = None  # ausente = pipeline padrão
    stages: dict[str, StageConfig] = Field(default_factory=dict)
