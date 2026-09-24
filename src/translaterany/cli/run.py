"""Comando run."""

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TaskID, TextColumn
from rich.table import Table

from translaterany.cli.app import (
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    AppState,
    all_checks,
    app,
    console,
    load_or_exit,
    print_checks,
)
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.lock import SeriesLocked
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.runner import Runner, RunSummary
from translaterany.pipeline.units import discover
from translaterany.util.doctor import has_failure, run_checks
from translaterany.util.log import LOGGER_NAME, setup_logging


@app.command()
def run(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série.")],
) -> None:
    """Executa o pipeline numa série."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    results = run_checks(all_checks(cfg))
    if has_failure(results):
        console.print("[red]Verificação de ambiente falhou:[/red]")
        print_checks(results)
        raise typer.Exit(EXIT_USAGE)
    setup_logging("DEBUG" if state.verbose else cfg.log_level, cfg.data_dir / "logs")

    try:
        series, episodes = discover(path)
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc
    console.print(f"Série: [bold]{series.name}[/bold] — {len(episodes)} episódio(s)")

    store = ArtifactStore(cfg.data_dir)
    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as progress:
        tasks: dict[str, TaskID] = {}

        def on_progress(stage: str, done: int, total: int) -> None:
            if stage not in tasks:
                tasks[stage] = progress.add_task(stage, total=total)
            progress.update(tasks[stage], completed=done)

        runner = Runner(cfg.stages, store, FakeLLM(), logging.getLogger(LOGGER_NAME), on_progress)
        try:
            summary = runner.run(series, episodes)
        except SeriesLocked as exc:
            console.print(f"[yellow]A série '{series.name}' já está sendo processada por outra execução.[/yellow]")
            raise typer.Exit(EXIT_FAILURE) from exc
        except ManifestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(EXIT_FAILURE) from exc
        except OSError as exc:
            logging.getLogger(LOGGER_NAME).debug("erro de E/S", exc_info=exc)
            console.print(f"[red]Erro de leitura/gravação: {exc}[/red]")
            raise typer.Exit(EXIT_FAILURE) from exc
        except KeyboardInterrupt as exc:
            console.print("[yellow]Interrompido. Rode o mesmo comando para retomar.[/yellow]")
            raise typer.Exit(EXIT_INTERRUPTED) from exc

    _print_summary(summary)
    raise typer.Exit(EXIT_FAILURE if summary.failed else EXIT_OK)


def _print_summary(summary: RunSummary) -> None:
    table = Table(title="Resumo")
    for column in ("Etapa", "Executadas", "Em cache", "Puladas", "Falhas"):
        table.add_column(column)
    for name, c in summary.stages.items():
        table.add_row(name, str(c.done), str(c.cached), str(c.skipped), str(c.failed))
    console.print(table)
