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
    from translaterany.config.dotenv import load_dotenv

    load_dotenv()

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

    profile_override = env.get("TRANSLATERANY_LLM_PROFILE") or env.get("LLM_PROFILE")
    if profile_override and profile_override in ("local", "hibrido", "nuvem"):
        raw.setdefault("llm", {})["profile"] = profile_override

    cloud_model = env.get("TRANSLATERANY_CLOUD_MODEL") or env.get("CLOUD_MODEL")
    model_tr = env.get("TRANSLATERANY_MODEL_TRANSLATE") or env.get("MODEL_TRANSLATE") or cloud_model
    model_rev = env.get("TRANSLATERANY_MODEL_REVIEW") or env.get("MODEL_REVIEW") or cloud_model

    think_env = env.get("TRANSLATERANY_LLM_THINK") or env.get("TRANSLATERANY_THINK") or env.get("LLM_THINK")
    think_override = think_env.strip().lower() in ("true", "1", "yes", "sim", "on") if think_env is not None else None

    if (
        model_tr
        or model_rev
        or think_override is not None
        or any(k.startswith("TRANSLATERANY_STAGE_") and k.endswith("_MODEL") for k in env)
    ):
        llm_raw = raw.setdefault("llm", {})
        models_raw = llm_raw.setdefault("models", {})
        profiles_raw = llm_raw.setdefault("profiles", {})

        if think_override is not None:
            for m_cfg in models_raw.values():
                if isinstance(m_cfg, dict):
                    m_cfg["think"] = think_override

        def _infer_provider(name: str) -> str:
            name_lower = name.lower()
            if "translategemma" in name_lower or "gemma" in name_lower or "qwen" in name_lower or "llama" in name_lower:
                return "ollama"
            if "gemini" in name_lower:
                return "gemini"
            if "gpt" in name_lower or "o1" in name_lower or "o3" in name_lower or "chatgpt" in name_lower:
                return "openai"
            if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
                return "gemini"
            if env.get("OPENAI_API_KEY"):
                return "openai"
            return "ollama"

        active_prof = llm_raw.get("profile", "nuvem")
        prof_cfg = profiles_raw.setdefault(active_prof, {})

        default_think = think_override if think_override is not None else False

        if model_tr:
            prov = _infer_provider(model_tr)
            models_raw[model_tr] = {
                "provider": prov,
                "model": model_tr,
                "num_ctx": 16384,
                "temperature": 0.3,
                "think": default_think,
            }
            prof_cfg["translate"] = model_tr

        if model_rev:
            prov = _infer_provider(model_rev)
            models_raw[model_rev] = {
                "provider": prov,
                "model": model_rev,
                "num_ctx": 16384,
                "temperature": 0.3,
                "think": default_think,
            }
            prof_cfg["review"] = model_rev

        # Sobrescrita específica de modelo por etapa (ex: TRANSLATERANY_STAGE_FINAL_READTHROUGH_MODEL=gpt-4o)
        for env_k, env_v in env.items():
            if env_k.startswith("TRANSLATERANY_STAGE_") and env_k.endswith("_MODEL") and env_v.strip():
                stage_part = env_k[len("TRANSLATERANY_STAGE_") : -len("_MODEL")].lower()
                st_model = env_v.strip()
                prov = _infer_provider(st_model)
                models_raw[st_model] = {
                    "provider": prov,
                    "model": st_model,
                    "num_ctx": 16384,
                    "temperature": 0.3,
                    "think": default_think,
                }
                raw.setdefault("stages", {}).setdefault(stage_part, {}).setdefault("options", {})["model"] = st_model


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
