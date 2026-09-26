"""Comando status."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.status import series_status

_COLORS = {"ok": "green", "skipped": "yellow", "failed": "red"}


def _track_name(store: ArtifactStore, series_key: str, episode_key: str | None) -> str:
    """Nome da faixa escolhida pelo select_track, se já existir."""
    if episode_key is None:
        return ""
    path = store.artifact_dir(series_key, episode_key) / "select_track.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["chosen"]["name"]
    except OSError, ValueError, KeyError:
        return ""


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
        if not store.series_dir(series.key).exists():
            console.print(f"Pasta nunca processada: {series.name}")
            return
        targets = [(series.key, series.name)]
    else:
        targets = [(info["key"], info["name"]) for info in store.known_series()]
    if not targets:
        console.print("Nenhuma série processada ainda.")
        return

    order = [s.name for s in cfg.stages]
    for key, name in targets:
        table = Table(title=name)
        for column in ("Unidade", "Status", "Última etapa", "Faixa", "Detalhe"):
            table.add_column(column)
        try:
            rows = series_status(store, key, order)
        except ManifestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(EXIT_FAILURE) from exc
        has_stale = False
        for row in rows:
            if row.stale:
                has_stale = True
            color = _COLORS.get(row.status, "white")
            unit = row.unit + (" (arquivo ausente)" if row.missing else "")
            track = _track_name(store, key, None if row.unit == "(série)" else row.unit)
            detail = row.detail or ""
            if row.stale and "glossário modificado" in detail:
                detail = f"[yellow]{detail}[/yellow]"
            table.add_row(unit, f"[{color}]{row.status}[/{color}]", row.last_done or "—", track, detail)
        console.print(table)
        if has_stale:
            console.print(
                "[yellow]Aviso: há episódios desatualizados devido a alterações no glossário. "
                "Use `translaterany retry <pasta> --stale` para reprocessá-los.[/yellow]"
            )
