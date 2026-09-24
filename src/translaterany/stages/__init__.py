"""Etapas embutidas. Importar este pacote registra todas elas no REGISTRY."""

from translaterany.stages import inventory  # noqa: F401

# Pipeline usado quando não há arquivo de configuração.
DEFAULT_PIPELINE: tuple[str, ...] = ("inventory",)
