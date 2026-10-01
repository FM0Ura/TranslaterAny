"""Comando doctor."""

import os

import typer

from translaterany.cli.app import EXIT_FAILURE, EXIT_OK, AppState, all_checks, app, print_checks
from translaterany.config import ConfigError, ResolvedConfig, load_config
from translaterany.config.model import ProviderConfig
from translaterany.util.doctor import (
    CheckResult,
    check_languagetool_service,
    check_nvidia_gpu,
    check_ollama_models,
    check_ollama_status,
    has_failure,
    run_checks,
)


def llm_doctor_checks(cfg: ResolvedConfig) -> list[tuple[str, CheckResult]]:
    results: list[tuple[str, CheckResult]] = []

    # 1. GPU Check
    gpu_ok, gpu_msg = check_nvidia_gpu()
    results.append(("gpu", CheckResult("ok" if gpu_ok else "warn", gpu_msg)))

    # 2. Ollama Connectivity & Models
    needs_local = cfg.llm.profile in ("local", "hibrido")
    pipeline_translates = any(stage.translates for stage in cfg.stages)
    required = needs_local and pipeline_translates

    ollama_provider = cfg.llm.providers.get("ollama", ProviderConfig())
    ollama_url = ollama_provider.base_url or "http://localhost:11434"
    status_ok, status_msg = check_ollama_status(ollama_url)
    results.append(("ollama", CheckResult("ok" if status_ok else ("fail" if required else "warn"), status_msg)))

    if status_ok:
        prof = cfg.llm.profiles.get(cfg.llm.profile)
        req_models: list[str] = []
        if prof:
            for key in (prof.translate, prof.review):
                m_cfg = cfg.llm.models.get(key)
                if m_cfg and m_cfg.provider == "ollama":
                    req_models.append(m_cfg.model)
        if not req_models:
            req_models = ["translategemma:12b", "gemma4:12b"]
        req_models = list(dict.fromkeys(req_models))

        models_ok, models_msg = check_ollama_models(ollama_url, req_models)
        results.append(
            (
                "ollama_models",
                CheckResult("ok" if models_ok else ("fail" if required else "warn"), models_msg),
            )
        )

    # 3. Optional Cloud Keys (Gemini / OpenAI)
    gemini_key = (
        cfg.llm.providers.get("gemini", ProviderConfig()).api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if gemini_key:
        results.append(("gemini", CheckResult("ok", "chave configurada")))
    elif cfg.llm.profile == "nuvem":
        results.append(("gemini", CheckResult("warn", "chave não configurada")))

    openai_key = cfg.llm.providers.get("openai", ProviderConfig()).api_key or os.environ.get("OPENAI_API_KEY")
    if openai_key:
        results.append(("openai", CheckResult("ok", "chave configurada")))
    elif cfg.llm.profile == "nuvem" and not gemini_key:
        results.append(("openai", CheckResult("fail", "perfil nuvem requer GEMINI_API_KEY ou OPENAI_API_KEY")))

    return results


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Verifica o ambiente (ferramentas, diretórios, configuração)."""
    state: AppState = ctx.obj
    try:
        cfg = load_config(state.config_path, state.data_dir)
    except ConfigError as exc:
        print_checks([("config", CheckResult("fail", str(exc)))])
        raise typer.Exit(EXIT_FAILURE) from exc
    where = str(cfg.source) if cfg.source else "padrão embutido"
    raw_results = [
        ("config", CheckResult("ok", f"configuração válida ({where})")),
        *run_checks(all_checks(cfg)),
        ("languagetool", check_languagetool_service()),
        *llm_doctor_checks(cfg),
    ]
    seen_names: set[str] = set()
    results: list[tuple[str, CheckResult]] = []
    for name, res in raw_results:
        if name not in seen_names:
            seen_names.add(name)
            results.append((name, res))
    print_checks(results)
    raise typer.Exit(EXIT_FAILURE if has_failure(results) else EXIT_OK)
