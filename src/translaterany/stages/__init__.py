"""Etapas embutidas. Importar este pacote registra todas elas no REGISTRY."""

from translaterany.stages import (  # noqa: F401
    classify,
    consolidate_memory,
    extract,
    extract_terms,
    inventory,
    merge_sentences,
    metadata,
    normalize,
    publish,
    remux,
    scene_analysis,
    select_track,
    translate_dialogue,
    translate_signs,
    translate_songs,
    translation_memory,
    write,
)

# Pipeline usado quando não há [pipeline] no config (remux vem desabilitado: enabled_by_default = False).
DEFAULT_PIPELINE: tuple[str, ...] = (
    "inventory",
    "metadata",
    "select_track",
    "extract",
    "normalize",
    "classify",
    "extract_terms",
    "consolidate_memory",
    "translate_dialogue",
    "write",
    "publish",
    "remux",
)
