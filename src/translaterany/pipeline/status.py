"""Leitura do estado das unidades a partir dos manifests (comando status)."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.subtitles.texts import UnitTexts


@dataclass(frozen=True)
class UnitStatus:
    unit: str  # chave do episódio, ou "(série)"
    status: str  # ok | skipped | failed
    last_done: str | None  # última etapa concluída, na ordem do pipeline
    detail: str | None  # motivo do pulo ou erro da falha
    missing: bool = False  # o arquivo de origem do episódio não existe mais
    stale: bool = False  # termos do glossário foram alterados após a tradução


def series_status(store: ArtifactStore, series_key: str, stage_order: Sequence[str]) -> list[UnitStatus]:
    rows: list[UnitStatus] = []
    units: list[tuple[str, str | None]] = [("(série)", None)]
    units += [(key, key) for key in store.episode_keys(series_key)]

    mem_dir = store.series_dir(series_key) / "memory"
    mem_store = MemoryStore(mem_dir)
    glossary = mem_store.load_glossary() if mem_dir.exists() else {}
    current_hashes = {term: entry.content_hash() for term, entry in glossary.items()}

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

        stale = False
        if episode_key is not None:
            rec = manifest.stages.get("translate_dialogue")
            if rec and rec.status == "done":
                art_path = store.artifact_dir(series_key, episode_key) / "translate_dialogue.json"
                if art_path.is_file():
                    try:
                        texts = UnitTexts.model_validate_json(art_path.read_text(encoding="utf-8"))
                        if texts.used_terms:
                            for term, used_hash in texts.used_terms.items():
                                if term not in current_hashes or current_hashes[term] != used_hash:
                                    stale = True
                                    break
                    except Exception:
                        pass

        if stale:
            if detail:
                detail = f"{detail} (glossário modificado)"
            else:
                detail = "desatualizado (glossário modificado)"

        rows.append(UnitStatus(label, manifest.status, done[-1] if done else None, detail, missing, stale))
    return rows
