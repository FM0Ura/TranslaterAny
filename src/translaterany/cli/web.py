"""Comando web: inicia o servidor da interface Web e API RESTful."""

from __future__ import annotations

import threading
import time
import webbrowser
from typing import Annotated

import typer
import uvicorn

from translaterany.cli.app import AppState, app, console
from translaterany.web.app import create_app


@app.command()
def web(
    ctx: typer.Context,
    host: Annotated[str, typer.Option("--host", "-h", help="Endereço de escuta do servidor.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Porta de escuta do servidor.")] = 8080,
    open_browser: Annotated[
        bool, typer.Option("--open-browser/--no-open-browser", help="Abre o navegador automaticamente.")
    ] = True,
    reload: Annotated[bool, typer.Option("--reload", help="Habilita auto-reload de desenvolvimento.")] = False,
) -> None:
    """Inicia o servidor da interface Web moderna e API RESTful desacoplada."""
    state: AppState | None = ctx.obj if ctx else None
    data_dir = state.data_dir if state else None
    config_path = state.config_path if state else None

    console.print(f"[bold green]✨ Iniciando TranslaterAny Web UI em http://{host}:{port}[/bold green]")
    console.print("[dim]Pressione Ctrl+C para encerrar o servidor.[/dim]")

    if open_browser:

        def _open() -> None:
            time.sleep(0.8)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    fastapi_app = create_app(data_dir=data_dir, config_path=config_path, start_worker=True)
    uvicorn.run(fastapi_app, host=host, port=port, reload=reload)
