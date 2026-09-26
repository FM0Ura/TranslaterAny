"""Comando retry."""

from pathlib import Path
from typing import Annotated

import typer

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.lock import SeriesLocked
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.reset import reset_from


@app.command()
def retry(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série.")],
    from_stage: Annotated[str, typer.Option("--from", help="Etapa a partir da qual reprocessar.")],
    episode: Annotated[str | None, typer.Option("--episode", help="Chave de um episódio específico.")] = None,
) -> None:
    """Força o reprocessamento a partir de uma etapa."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    try:
        series, episodes = discover(path)
        count = reset_from(ArtifactStore(cfg.data_dir), series, episodes, cfg.stages, from_stage, episode)
    except (NotADirectoryError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_FAILURE) from exc
    except SeriesLocked as exc:
        console.print(f"[yellow]A série '{series.name}' está sendo processada por outra execução.[/yellow]")
        raise typer.Exit(EXIT_FAILURE) from exc
    console.print(f"{count} unidade(s) reaberta(s) a partir de '{from_stage}'.")
    console.print("Rode `translaterany run` para reprocessar.")
