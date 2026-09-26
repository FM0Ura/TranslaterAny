"""Comando retry."""

from pathlib import Path
from typing import Annotated

import typer

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.lock import SeriesLocked
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.reset import reset_from, reset_stale


@app.command()
def retry(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série.")],
    from_stage: Annotated[str | None, typer.Option("--from", help="Etapa a partir da qual reprocessar.")] = None,
    episode: Annotated[str | None, typer.Option("--episode", help="Chave de um episódio específico.")] = None,
    stale: Annotated[
        bool,
        typer.Option("--stale", help="Reseta episódios com termos de glossário desatualizados."),
    ] = False,
) -> None:
    """Força o reprocessamento a partir de uma etapa ou por termos desatualizados de glossário."""
    if not stale and from_stage is None:
        console.print("[red]Opção --from é obrigatória quando --stale não for utilizado.[/red]")
        raise typer.Exit(EXIT_USAGE)

    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    try:
        series, episodes = discover(path)
        if stale:
            targets = [ep for ep in episodes if episode is None or ep.key == episode]
            if episode is not None and not targets:
                raise ValueError(f"episódio '{episode}' não encontrado na série")
            count = reset_stale(ArtifactStore(cfg.data_dir), series, targets, cfg.stages)
            console.print(f"{count} episódio(s) desatualizado(s) reaberto(s) a partir de 'translate_dialogue'.")
            console.print("Rode `translaterany run` para reprocessar.")
            return

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
