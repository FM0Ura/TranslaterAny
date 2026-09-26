"""CLI do TranslaterAny. Importar os módulos de comando os registra no app."""

from translaterany.cli import doctor, estimate, retry, run, status  # noqa: F401
from translaterany.cli.app import app

__all__ = ["app"]
