"""Comando doctor."""

import typer

from translaterany.cli.app import EXIT_FAILURE, EXIT_OK, AppState, all_checks, app, print_checks
from translaterany.config import ConfigError, load_config
from translaterany.util.doctor import CheckResult, has_failure, run_checks


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
    results = [("config", CheckResult("ok", f"configuração válida ({where})")), *run_checks(all_checks(cfg))]
    print_checks(results)
    raise typer.Exit(EXIT_FAILURE if has_failure(results) else EXIT_OK)
