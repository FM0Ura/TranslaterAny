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
from translaterany.config import ResolvedConfig
from translaterany.library import SeriesScan, scan_library
from translaterany.llm import PydanticAIClient
from translaterany.llm.pricing import price_lookup
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.lock import SeriesLocked
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.runner import Runner, RunSummary
from translaterany.util.doctor import has_failure, run_checks
from translaterany.util.log import LOGGER_NAME, setup_logging


@app.command()
def run(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série ou da biblioteca.")],
    force: Annotated[bool, typer.Option("--force", help="Reabre pulados e sobrescreve PT-BR de terceiros.")] = False,
    source: Annotated[str | None, typer.Option("--source", "-s", help="Idioma de origem (ex: en, ja).")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t", help="Idioma de destino (ex: pt-BR, es).")] = None,
) -> None:
    """Executa o pipeline numa série ou em todas as séries de uma biblioteca."""
    from translaterany.languages.registry import LanguageRegistry

    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    source_lang = LanguageRegistry.resolve(source) if source else LanguageRegistry.resolve(cfg.source_language)
    target_lang = LanguageRegistry.resolve(target) if target else LanguageRegistry.resolve(cfg.target_language)
    results = run_checks(all_checks(cfg))
    if has_failure(results):
        console.print("[red]Verificação de ambiente falhou:[/red]")
        print_checks(results)
        raise typer.Exit(EXIT_USAGE)
    setup_logging("DEBUG" if state.verbose else cfg.log_level, cfg.data_dir / "logs")

    try:
        scans = scan_library(path, min_file_age=cfg.min_file_age)
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc
    if not scans:
        console.print(f"Nenhuma série encontrada em {path}.")
        raise typer.Exit(EXIT_OK)

    failed = False
    for scan in scans:
        failed |= not _run_series(scan, cfg, force, source_lang, target_lang)
    raise typer.Exit(EXIT_FAILURE if failed else EXIT_OK)


def _run_series(
    scan: SeriesScan,
    cfg: ResolvedConfig,
    force: bool,
    source_lang: Any = None,
    target_lang: Any = None,
) -> bool:
    """Processa uma série; devolve False se algo falhou."""
    series = scan.series
    console.print(f"Série: [bold]{series.name}[/bold] — {len(scan.episodes)} episódio(s)")
    for warning in scan.warnings:
        console.print(f"  [yellow]aviso:[/yellow] {warning}")
    for ignored in scan.ignored:
        console.print(f"  [dim]ignorado nesta execução: {ignored.path.name} — {ignored.reason}[/dim]")
    if scan.error:
        console.print(f"  [red]{scan.error}[/red]")
        return False

    log = logging.getLogger(LOGGER_NAME)
    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as progress:
        tasks: dict[str, TaskID] = {}

        def on_progress(stage: str, done: int, total: int) -> None:
            if stage not in tasks:
                tasks[stage] = progress.add_task(stage, total=total)
            progress.update(tasks[stage], completed=done)

        runner = Runner(
            cfg.stages,
            ArtifactStore(cfg.data_dir),
            PydanticAIClient(cfg.llm),
            log,
            on_progress,
            prices=price_lookup(cfg.llm),
            source_language=source_lang,
            target_language=target_lang,
        )
        try:
            summary = runner.run(series, scan.episodes, force=force)
        except SeriesLocked:
            console.print(f"  [yellow]A série '{series.name}' já está sendo processada por outra execução.[/yellow]")
            return False
        except ManifestError as exc:
            console.print(f"  [red]{exc}[/red]")
            return False
        except OSError as exc:
            log.debug("erro de E/S", exc_info=exc)
            console.print(f"  [red]Erro de leitura/gravação: {exc}[/red]")
            return False
        except KeyboardInterrupt as exc:
            console.print("[yellow]Interrompido. Rode o mesmo comando para retomar.[/yellow]")
            raise typer.Exit(EXIT_INTERRUPTED) from exc

    _print_summary(series.name, summary)
    return not summary.failed


def _print_summary(name: str, summary: RunSummary) -> None:
    table = Table(title=f"Resumo — {name}")
    for column in ("Etapa", "Executadas", "Em cache", "Puladas", "Falhas"):
        table.add_column(column)
    for stage, c in summary.stages.items():
        table.add_row(stage, str(c.done), str(c.cached), str(c.skipped), str(c.failed))
    console.print(table)
