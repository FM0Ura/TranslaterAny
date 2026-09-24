"""Configuração de logging: terminal (rich) + arquivo por execução."""

import logging
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler

LOGGER_NAME = "translaterany"


def setup_logging(level: str, log_dir: Path | None) -> Path | None:
    """Configura o logger raiz do app. Devolve o caminho do arquivo de log (se houver)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console = RichHandler(show_path=False, rich_tracebacks=False)
    console.setLevel(level)
    logger.addHandler(console)

    if log_dir is None:
        return None
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(file_handler)
    return log_file
