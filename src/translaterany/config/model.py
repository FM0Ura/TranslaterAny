"""Formato do arquivo de configuração (config.toml)."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneralConfig(_Strict):
    data_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class PipelineConfig(_Strict):
    stages: list[str]


class StageConfig(_Strict):
    enabled: bool = True
    options: dict[str, Any] = Field(default_factory=dict)


class AppConfig(_Strict):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    pipeline: PipelineConfig
    stages: dict[str, StageConfig] = Field(default_factory=dict)
