"""Etapas embutidas. Importar este pacote registra todas elas no REGISTRY."""

from translaterany.stages import (  # noqa: F401
    classify,
    extract,
    inventory,
    normalize,
    publish,
    remux,
    select_track,
    translate_dialogue,
    write,
)

# Pipeline usado quando não há [pipeline] no config (remux vem desabilitado: enabled_by_default = False).
DEFAULT_PIPELINE: tuple[str, ...] = (
    "inventory",
    "select_track",
    "extract",
    "normalize",
    "classify",
    "translate_dialogue",
    "write",
    "publish",
    "remux",
)
