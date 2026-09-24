"""Comando status."""

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.status import series_status
from translaterany.pipeline.units import discover

_COLORS = {"ok": "green", "skipped": "yellow", "failed": "red"}


@app.command()
def status(
    ctx: typer.Context,
    path: Annotated[Path | None, typer.Argument(help="Pasta da série (padrão: todas).")] = None,
) -> None:
    """Mostra o estado dos episódios."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    store = ArtifactStore(cfg.data_dir)
    if path is not None:
        try:
            series, _ = discover(path)
        except NotADirectoryError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(EXIT_USAGE) from exc
        targets = [(series.key, series.name)]
    else:
        targets = [(info["key"], info["name"]) for info in store.known_series()]
    if not targets:
        console.print("Nenhuma série processada ainda.")
        return

    order = [s.name for s in cfg.stages]
    for key, name in targets:
        table = Table(title=name)
        for column in ("Unidade", "Status", "Última etapa", "Detalhe"):
            table.add_column(column)
        try:
            rows = series_status(store, key, order)
        except ManifestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(EXIT_FAILURE) from exc
        for row in rows:
            color = _COLORS.get(row.status, "white")
            table.add_row(row.unit, f"[{color}]{row.status}[/{color}]", row.last_done or "—", row.detail or "")
        console.print(table)
