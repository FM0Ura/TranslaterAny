"""Chave de cache de uma etapa para uma unidade."""

from collections.abc import Mapping, Sequence
from typing import Any

from translaterany.pipeline.stage import Stage
from translaterany.util.fs import canonical_json, sha256_bytes


def compute_key(
    stage: Stage,
    input_hashes: Mapping[str, str],
    source_fingerprint: str | None,
    episode_set: Sequence[str] | None = None,
    extra: Any = None,
) -> str:
    """`episode_set`: chaves dos episódios da série (só para etapas de série, que veem `ctx.episodes`)."""
    payload = {
        "stage": stage.name,
        "version": stage.version,
        "options": stage.options.model_dump(mode="json"),
        "inputs": dict(sorted(input_hashes.items())),
        "source": source_fingerprint,
        "episodes": sorted(episode_set) if episode_set is not None else None,
        "extra": extra,  # Stage.cache_payload(): dados de fora do diretório de dados (ex.: series.toml)
    }
    return sha256_bytes(canonical_json(payload))


def combine_hashes(pairs: Mapping[str, str]) -> str:
    """Hash de um conjunto (episódio -> hash), usado quando uma etapa de série lê etapas por episódio."""
    return sha256_bytes(canonical_json(sorted(pairs.items())))
