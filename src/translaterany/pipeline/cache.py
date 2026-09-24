"""Chave de cache de uma etapa para uma unidade."""

from collections.abc import Mapping

from translaterany.pipeline.stage import Stage
from translaterany.util.fs import canonical_json, sha256_bytes


def compute_key(stage: Stage, input_hashes: Mapping[str, str], source_fingerprint: str | None) -> str:
    payload = {
        "stage": stage.name,
        "version": stage.version,
        "options": stage.options.model_dump(mode="json"),
        "inputs": dict(sorted(input_hashes.items())),
        "source": source_fingerprint,
    }
    return sha256_bytes(canonical_json(payload))


def combine_hashes(pairs: Mapping[str, str]) -> str:
    """Hash de um conjunto (episódio -> hash), usado quando uma etapa de série lê etapas por episódio."""
    return sha256_bytes(canonical_json(sorted(pairs.items())))
