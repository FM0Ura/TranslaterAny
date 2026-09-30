"""Formato do arquivo de configuração (config.toml)."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfig(_Strict):
    base_url: str | None = None
    api_key: str | None = None


class ModelConfig(_Strict):
    provider: str
    model: str
    num_ctx: int = 4096
    temperature: float = 0.3
    think: bool = False  # raciocínio de modelos "thinking" (ex.: gemma4); desligado gasta bem menos tokens
    input_price_per_mtok: float = 0.0  # USD por milhão de tokens de entrada
    output_price_per_mtok: float = 0.0  # USD por milhão de tokens de saída


class ProfileConfig(_Strict):
    translate: str = "translategemma"
    review: str = "gemma4"
    options: dict[str, Any] = Field(default_factory=dict)


class LLMConfig(_Strict):
    profile: Literal["local", "hibrido", "nuvem"] = "local"
    max_cost_usd: float = 5.0
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "ollama": ProviderConfig(base_url="http://localhost:11434/v1", api_key="ollama"),
            "gemini": ProviderConfig(api_key=None),
            "openai": ProviderConfig(api_key=None),
        }
    )
    models: dict[str, ModelConfig] = Field(
        default_factory=lambda: {
            "translategemma": ModelConfig(provider="ollama", model="translategemma:12b", num_ctx=8192, temperature=0.3),
            "gemma4": ModelConfig(provider="ollama", model="gemma4:12b", num_ctx=16384, temperature=0.7),
        }
    )
    profiles: dict[str, ProfileConfig] = Field(
        default_factory=lambda: {
            "local": ProfileConfig(translate="translategemma", review="gemma4"),
            "hibrido": ProfileConfig(translate="translategemma", review="gemma4"),
            "nuvem": ProfileConfig(translate="translategemma", review="gemma4"),
        }
    )


class GeneralConfig(_Strict):
    data_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class DiscoveryConfig(_Strict):
    min_file_age: float = 120


class PipelineConfig(_Strict):
    stages: list[str]


class StageConfig(_Strict):
    enabled: bool | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class TranslationConfig(_Strict):
    honorifics: Literal["keep", "adapt", "remove"] = "keep"
    profanity: Literal["faithful", "soften", "raw"] = "faithful"


class ChecksConfig(_Strict):
    """Limites das checagens (M5). Padrão Netflix PT-BR para velocidade de leitura."""

    max_cps: float = Field(17.0, gt=0)
    max_cpl: int = Field(42, gt=0)
    max_lines: int = Field(2, ge=1)
    length_ratio: tuple[float, float] = (0.5, 2.0)
    length_ratio_min_chars: int = Field(10, ge=0)
    disabled: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_length_ratio(self) -> ChecksConfig:
        low, high = self.length_ratio
        if not 0 < low <= high:
            raise ValueError("length_ratio deve ter 0 < mínimo <= máximo")
        return self


class AppConfig(_Strict):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    pipeline: PipelineConfig | None = None
    stages: dict[str, StageConfig] = Field(default_factory=dict)

