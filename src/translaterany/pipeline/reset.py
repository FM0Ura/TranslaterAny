"""Reprocessamento forçado (comando retry)."""

from collections.abc import Sequence

from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore, ManifestSet
from translaterany.pipeline.lock import SeriesLock
from translaterany.pipeline.stage import Stage, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.texts import UnitTexts


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


def reset_stale(
    store: ArtifactStore,
    series: Series,
    episodes: Sequence[Episode],
    stages: Sequence[Stage] | None = None,
) -> int:
    """Reseta especificamente os episódios que consumiram termos de glossário cujo hash
    de conteúdo mudou em glossary.yaml (ou não existem mais no glossário).

    Apaga do manifest a etapa 'translate_dialogue' e todas as seguintes e reabre
    os episódios desatualizados.
    Retorna a quantidade de episódios resetados.
    """
    if stages is not None and "translate_dialogue" in [s.name for s in stages]:
        names = [s.name for s in stages]
        start = names.index("translate_dialogue")
        affected = names[start:]
    else:
        affected = ["translate_dialogue", "write", "publish", "remux"]

    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)
    glossary = mem_store.load_glossary()
    current_hashes = {term: entry.content_hash() for term, entry in glossary.items()}

    stale_episodes: list[Episode] = []
    for ep in episodes:
        art_path = store.artifact_dir(series.key, ep.key) / "translate_dialogue.json"
        if not art_path.is_file():
            continue
        try:
            texts = UnitTexts.model_validate_json(art_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not texts.used_terms:
            continue

        is_stale = False
        for term, used_hash in texts.used_terms.items():
            if term not in current_hashes or current_hashes[term] != used_hash:
                is_stale = True
                break
        if is_stale:
            stale_episodes.append(ep)

    if not stale_episodes:
        return 0

    with SeriesLock(store.lock_path(series.key)):
        manifests = ManifestSet(store, series, episodes)
        for ep in stale_episodes:
            manifest = manifests.get(ep)
            for name in affected:
                manifest.stages.pop(name, None)
            manifest.status = "ok"
            manifest.skip_reason = None
            manifests.save(ep)

    return len(stale_episodes)
