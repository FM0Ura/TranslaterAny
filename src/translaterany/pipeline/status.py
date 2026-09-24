"""Leitura do estado das unidades a partir dos manifests (comando status)."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from translaterany.pipeline.artifacts import ArtifactStore


@dataclass(frozen=True)
class UnitStatus:
    unit: str  # chave do episódio, ou "(série)"
    status: str  # ok | skipped | failed
    last_done: str | None  # última etapa concluída, na ordem do pipeline
    detail: str | None  # motivo do pulo ou erro da falha
    missing: bool = False  # o arquivo de origem do episódio não existe mais


def series_status(store: ArtifactStore, series_key: str, stage_order: Sequence[str]) -> list[UnitStatus]:
    rows: list[UnitStatus] = []
    units: list[tuple[str, str | None]] = [("(série)", None)]
    units += [(key, key) for key in store.episode_keys(series_key)]
    for label, episode_key in units:
        manifest = store.read_manifest(series_key, episode_key)
        if manifest is None:
            continue
        done = [name for name in stage_order if (r := manifest.stages.get(name)) and r.status == "done"]
        failed = [r for r in manifest.stages.values() if r.status == "failed"]
        detail = manifest.skip_reason
        if manifest.status == "failed" and failed:
            detail = failed[-1].error
        missing = episode_key is not None and bool(manifest.unit.source) and not Path(manifest.unit.source).exists()
        rows.append(UnitStatus(label, manifest.status, done[-1] if done else None, detail, missing))
    return rows
