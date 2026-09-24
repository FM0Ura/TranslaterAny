"""Reprocessamento forçado (comando retry)."""

from collections.abc import Sequence

from translaterany.pipeline.artifacts import ArtifactStore, ManifestSet
from translaterany.pipeline.lock import SeriesLock
from translaterany.pipeline.stage import Stage, StageScope
from translaterany.pipeline.units import Episode, Series


def reset_from(
    store: ArtifactStore,
    series: Series,
    episodes: Sequence[Episode],
    stages: Sequence[Stage],
    from_stage: str,
    episode_key: str | None = None,
) -> int:
    """Apaga do manifest a etapa `from_stage` e todas as seguintes (de qualquer escopo) e
    reabre as unidades afetadas. Os artefatos não são apagados; serão sobrescritos.

    Retorna o número de unidades (série e/ou episódios) reabertas.
    """
    names = [s.name for s in stages]
    if from_stage not in names:
        raise ValueError(f"etapa '{from_stage}' não está no pipeline ativo")
    start = names.index(from_stage)
    if episode_key is not None and stages[start].scope is StageScope.SERIES:
        raise ValueError(f"'{from_stage}' é uma etapa de série; não use --episode com ela")
    targets = [ep for ep in episodes if episode_key is None or ep.key == episode_key]
    if episode_key is not None and not targets:
        raise ValueError(f"episódio '{episode_key}' não encontrado na série")
    affected = names[start:]

    with SeriesLock(store.lock_path(series.key)):
        manifests = ManifestSet(store, series, episodes)
        units: list[Episode | None] = [*targets]
        if episode_key is None:
            units.append(None)
        for unit in units:
            manifest = manifests.get(unit)
            for name in affected:
                manifest.stages.pop(name, None)
            manifest.status = "ok"
            manifest.skip_reason = None
            manifests.save(unit)
    return len(units)
