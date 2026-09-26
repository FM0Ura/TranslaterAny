"""App typer, opções globais e utilitários compartilhados pelos comandos."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from translaterany.config import ConfigError, ResolvedConfig, load_config
from translaterany.util.doctor import Check, CheckResult, data_dir_check, python_version_check

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Tradução de legendas de anime EN → PT-BR.")
console = Console()

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


@dataclass
class AppState:
    config_path: Path | None = None
    data_dir: Path | None = None
    verbose: bool = False


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[Path | None, typer.Option("--config", help="Arquivo de configuração.")] = None,
    data_dir: Annotated[Path | None, typer.Option("--data-dir", help="Diretório de dados.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log detalhado.")] = False,
) -> None:
    ctx.obj = AppState(config_path=config, data_dir=data_dir, verbose=verbose)


def load_or_exit(state: AppState) -> ResolvedConfig:
    try:
        return load_config(state.config_path, state.data_dir)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc


def all_checks(cfg: ResolvedConfig) -> list[Check]:
    checks: list[Check] = [python_version_check(), data_dir_check(cfg.data_dir)]
    for stage in cfg.stages:
        checks.extend(stage.doctor_checks())
    return checks


_ICONS = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}


def print_checks(results: list[tuple[str, CheckResult]]) -> None:
    table = Table(show_header=False, box=None)
    for name, result in results:
        table.add_row(_ICONS[result.status], name, result.message)
    console.print(table)


from translaterany.cli import doctor, estimate, retry, run, status  # noqa: E402, F401

