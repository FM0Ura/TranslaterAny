"""Formato do arquivo de configuração (config.toml)."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigError(ValueError):
    """Configuração inválida. A mensagem já vem pronta para o usuário (PT-BR)."""


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


class LibraryConfig(_Strict):
    path: Path | None = None


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


class TreatmentConsistencyOptions(_Strict):
    """Opções da etapa treatment_consistency (M7)."""

    model: str = "review"
    max_lines_per_block: int = 30


class AdaptOptions(_Strict):
    """Opções da etapa adapt (M7)."""

    model: str = "review"
    max_lines_per_block: int = 30
    max_cps: float = Field(17.0, gt=0)


class OrthographyOptions(_Strict):
    """Opções da etapa orthography (M7)."""

    url: str = "http://localhost:8010/v2/check"
    timeout_s: float = Field(5.0, gt=0)
    language: str = "pt-BR"


class FinalReadthroughOptions(_Strict):
    """Opções da etapa final_readthrough (M7)."""

    model: str = "review"
    max_lines_per_block: int = 30


class GatesConfig(_Strict):
    """Configuração dos portões de etapa (M8)."""

    enabled: bool = True
    max_retries: int = Field(2, ge=0)


class QALoopOptions(_Strict):
    """Opções da etapa qa_loop (M8)."""

    max_rounds: int = Field(2, ge=1)
    max_extra_calls: int = Field(30, ge=0)
    warn_edit_rate_threshold: float = Field(0.25, ge=0.0, le=1.0)


_STAGE_OPTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "qa_loop": {
        "max_rounds": 2,
        "max_extra_calls": 30,
        "warn_edit_rate_threshold": 0.25,
    },
}


class StagesDict(dict[str, StageConfig]):
    """Dicionário de configurações de etapas com padrões embutidos."""

    def __getitem__(self, key: str) -> StageConfig:
        if super().__contains__(key):
            cfg = super().__getitem__(key)
            if key in _STAGE_OPTION_DEFAULTS:
                for k, v in _STAGE_OPTION_DEFAULTS[key].items():
                    cfg.options.setdefault(k, v)
            return cfg
        if key in _STAGE_OPTION_DEFAULTS:
            return StageConfig(options=dict(_STAGE_OPTION_DEFAULTS[key]))
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return super().__contains__(key) or key in _STAGE_OPTION_DEFAULTS


class AppConfig(_Strict):
    source_language: str = "en"
    target_language: str = "pt-BR"
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    library: LibraryConfig = Field(default_factory=LibraryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    pipeline: PipelineConfig | None = None
    stages: dict[str, StageConfig] = Field(default_factory=StagesDict)

    @model_validator(mode="after")
    def _validate_languages(self) -> AppConfig:
        from translaterany.languages.registry import LanguageRegistry

        src = LanguageRegistry.resolve(self.source_language)
        tgt = LanguageRegistry.resolve(self.target_language)
        if src.code == tgt.code:
            raise ValueError("idioma de origem e destino não podem ser iguais")
        return self

    @model_validator(mode="after")
    def _wrap_stages(self) -> AppConfig:
        if not isinstance(self.stages, StagesDict):
            self.stages = StagesDict(self.stages)
        return self

