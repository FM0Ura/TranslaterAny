"""Localiza, lê e valida a configuração, e instancia as etapas habilitadas."""

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from translaterany.config.model import AppConfig, LLMConfig, PipelineConfig, TranslationConfig
from translaterany.pipeline.registry import REGISTRY, StageRegistry
from translaterany.pipeline.stage import Stage, StageScope

CONFIG_ENV = "TRANSLATERANY_CONFIG"


class ConfigError(ValueError):
    """Configuração inválida. A mensagem já vem pronta para o usuário (PT-BR)."""


@dataclass(frozen=True)
class ResolvedConfig:
    source: Path | None  # arquivo lido, ou None se usou o padrão embutido
    data_dir: Path
    log_level: str
    stages: tuple[Stage, ...]  # habilitadas, na ordem, já instanciadas
    min_file_age: float = 120
    llm: LLMConfig = field(default_factory=LLMConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    app: AppConfig | None = None
    source_language: str = "en"
    target_language: str = "pt-BR"


def default_config_path(env: Mapping[str, str] = os.environ) -> Path:
    base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / "translaterany" / "config.toml"


def default_data_dir(env: Mapping[str, str] = os.environ) -> Path:
    base = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else Path.home() / ".local" / "share"
    return base / "translaterany"


def find_config(explicit: Path | None, env: Mapping[str, str] = os.environ) -> Path | None:
    """Ordem: --config > $TRANSLATERANY_CONFIG > XDG (se existir) > None (padrão embutido)."""
    if explicit is not None:
        if not explicit.exists():
            raise ConfigError(f"arquivo de configuração não encontrado: {explicit}")
        return explicit
    if env.get(CONFIG_ENV):
        path = Path(env[CONFIG_ENV])
        if not path.exists():
            raise ConfigError(f"{CONFIG_ENV} aponta para arquivo inexistente: {path}")
        return path
    path = default_config_path(env)
    return path if path.exists() else None


def load_config_from_str(toml_text: str) -> AppConfig:
    """Lê e valida uma string TOML diretamente em um AppConfig."""
    raw: dict[str, Any] = {}
    if toml_text.strip():
        try:
            raw = tomllib.loads(toml_text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Erro no config: TOML inválido — {exc}") from exc
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_errors("config string", exc)) from exc


def load_config(
    explicit: Path | None = None,
    data_dir_override: Path | None = None,
    *,
    registry: StageRegistry = REGISTRY,
    default_pipeline: Sequence[str] | None = None,
    env: Mapping[str, str] = os.environ,
) -> ResolvedConfig:
    if default_pipeline is None:
        from translaterany.stages import DEFAULT_PIPELINE  # registra as etapas embutidas

        default_pipeline = DEFAULT_PIPELINE
    path = find_config(explicit, env)
    raw: dict[str, Any] = {"pipeline": {"stages": list(default_pipeline)}}
    if path is not None:
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Erro no config ({path}): TOML inválido — {exc}") from exc
    where = str(path) if path else "config padrão"

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_errors(where, exc)) from exc

    if config.pipeline is None:
        config.pipeline = PipelineConfig(stages=list(default_pipeline))

    from translaterany.checks import check_names  # import tardio: checks depende de config.model

    unknown = sorted(set(config.checks.disabled) - check_names())
    if unknown:
        raise ConfigError(
            _format(
                where,
                [
                    f"checks.disabled: checagem desconhecida {', '.join(unknown)} "
                    f"(disponíveis: {', '.join(sorted(check_names()))})"
                ],
            )
        )

    stages = _build_stages(config, registry, where)
    data_dir = data_dir_override or config.general.data_dir or default_data_dir(env)
    return ResolvedConfig(
        source=path,
        data_dir=Path(data_dir).expanduser(),
        log_level=config.general.log_level,
        stages=tuple(stages),
        min_file_age=config.discovery.min_file_age,
        llm=config.llm,
        translation=config.translation,
        app=config,
        source_language=config.source_language,
        target_language=config.target_language,
    )


def _build_stages(config: AppConfig, registry: StageRegistry, where: str) -> list[Stage]:
    errors: list[str] = []
    order = config.pipeline.stages

    seen: set[str] = set()
    for name in order:
        if name not in registry:
            errors.append(f"pipeline.stages: etapa desconhecida '{name}' (disponíveis: {', '.join(registry.names())})")
        if name in seen:
            errors.append(f"pipeline.stages: etapa '{name}' aparece mais de uma vez")
        seen.add(name)
    for name in config.stages:
        if name not in order:
            errors.append(f"stages.{name}: seção para etapa que não está em pipeline.stages")
    if errors:
        raise ConfigError(_format(where, errors))

    enabled: list[str] = [n for n in order if _is_enabled(config, registry, n)]
    stages: list[Stage] = []
    available: set[str] = set()
    for name in order:
        cls = registry.get(name)
        stage_cfg = config.stages.get(name)
        options_raw = stage_cfg.options if stage_cfg else {}
        try:
            options = cls.Options.model_validate(options_raw)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"stages.{name}.options.{loc}: {_translate_pydantic_error(err)}")
            continue
        if name not in enabled:
            continue
        if cls.reads_source and cls.scope is StageScope.SERIES:
            errors.append(f"stages.{name}: reads_source não é suportado em etapas de série")
        stage = cls(options)  # as entradas podem depender das opções (ex.: write.text_source)
        stage.bind_pipeline(tuple(stages), config)
        for dep in stage.inputs:
            if dep not in available:
                if dep not in order:
                    reason = "não está no pipeline"
                elif dep not in enabled:
                    reason = "está desabilitada"
                else:
                    reason = "não vem antes dela no pipeline"
                errors.append(f"stages.{name}: depende de '{dep}', que {reason}")
        stages.append(stage)
        available.add(name)
    if errors:
        raise ConfigError(_format(where, errors))
    return stages


def _is_enabled(config: AppConfig, registry: StageRegistry, name: str) -> bool:
    section = config.stages.get(name)
    if section is not None and section.enabled is not None:
        return section.enabled
    return registry.get(name).enabled_by_default


def _translate_pydantic_error(err: dict[str, Any]) -> str:
    loc = ".".join(str(p) for p in err.get("loc", []))
    err_type = err.get("type", "")
    inp = err.get("input")
    ctx = err.get("ctx", {})

    if loc in ("llm.profile", "profile"):
        return f"Campo inválido: Perfil de IA desconhecido '{inp}'. Opções válidas: 'local', 'hibrido', 'nuvem'."
    if err_type == "extra_forbidden":
        return "Campo desconhecido não permitido"
    if err_type == "missing":
        return "Campo obrigatório ausente"
    if "literal" in err_type:
        expected = ctx.get("expected", "")
        return f"Campo inválido: valor deve ser um de {expected}"
    if "type" in err_type:
        expected = ctx.get("expected", "")
        return f"Campo inválido: tipo incorreto (esperado {expected})" if expected else "Campo inválido: tipo incorreto"
    return f"Campo inválido: {err.get('msg', 'valor inválido')}"


def _format_errors(where: str, exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(raiz)"
        msg = _translate_pydantic_error(err)
        lines.append(f"{loc}: {msg}")
    return _format(where, lines)


def _format(where: str, errors: Sequence[str]) -> str:
    return f"Erro no config ({where}):\n" + "\n".join(f"  {e}" for e in errors)
