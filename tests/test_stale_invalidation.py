from pathlib import Path
from types import SimpleNamespace

from translaterany.memory.models import GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import ManifestSet
from translaterany.pipeline.reset import reset_stale
from translaterany.pipeline.status import series_status
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.texts import UnitTexts


def test_stale_detection_and_reset(tmp_path: Path):
    store = ArtifactStore(tmp_path / "data")
    series = Series(name="Charlotte (2015)", path=tmp_path)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)

    # 1. Salva glossary inicial
    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)
    entry = GlossaryEntry(term="Plunder", translation="Pilhar")
    mem_store.save_glossary([entry])
    initial_hash = entry.content_hash()

    # 2. Grava artefato translate_dialogue com initial_hash
    art_dir = store.artifact_dir(series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)
    texts = UnitTexts(texts={"0": "Pilhar"}, used_terms={"Plunder": initial_hash})
    (art_dir / "translate_dialogue.json").write_text(texts.model_dump_json(), encoding="utf-8")

    # 3. Cria manifest com status done
    manifests = ManifestSet(store, series, [ep])
    manifests.episodes[ep.key].stages["translate_dialogue"] = SimpleNamespace(
        status="done", key="k", artifact="translate_dialogue.json", artifact_hash="h"
    )
    manifests.save(ep)

    # 4. Modifica termo no glossary.yaml
    updated_entry = GlossaryEntry(term="Plunder", translation="Saque")
    mem_store.save_glossary([updated_entry])

    # 5. Executa reset_stale
    reset_count = reset_stale(store, series, [ep])
    assert reset_count == 1

    # 6. Verifica que manifest teve translate_dialogue removido/resetado
    reloaded_manifest = store.load_manifest(series.key, ep.key)
    assert "translate_dialogue" not in reloaded_manifest.stages


def test_series_status_detects_stale_episode(tmp_path: Path):
    store = ArtifactStore(tmp_path / "data")
    series = Series(name="Charlotte (2015)", path=tmp_path)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)

    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)
    entry = GlossaryEntry(term="Plunder", translation="Pilhar")
    mem_store.save_glossary([entry])
    initial_hash = entry.content_hash()

    art_dir = store.artifact_dir(series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)
    texts = UnitTexts(texts={"0": "Pilhar"}, used_terms={"Plunder": initial_hash})
    (art_dir / "translate_dialogue.json").write_text(texts.model_dump_json(), encoding="utf-8")

    manifests = ManifestSet(store, series, [ep])
    manifests.episodes[ep.key].stages["translate_dialogue"] = SimpleNamespace(
        status="done", key="k", artifact="translate_dialogue.json", artifact_hash="h"
    )
    manifests.save(ep)

    # Antes de modificar, não está stale
    rows = series_status(store, series.key, ["translate_dialogue"])
    ep_row = next(r for r in rows if r.unit == ep.key)
    assert not ep_row.stale

    # Modifica o termo no glossary.yaml
    updated_entry = GlossaryEntry(term="Plunder", translation="Saque")
    mem_store.save_glossary([updated_entry])

    # Agora deve detectar como stale
    rows_after = series_status(store, series.key, ["translate_dialogue"])
    ep_row_after = next(r for r in rows_after if r.unit == ep.key)
    assert ep_row_after.stale
    assert "glossário modificado" in ep_row_after.detail


def test_cli_retry_stale(tmp_path: Path):
    from typer.testing import CliRunner

    from translaterany.cli.app import app
    from translaterany.library import discover

    data_dir = tmp_path / "data"
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir(parents=True)
    ep_file = series_dir / "S01E01.mkv"
    ep_file.write_bytes(b"dummy")

    series, episodes = discover(series_dir)
    ep = episodes[0]
    store = ArtifactStore(data_dir)

    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)
    entry = GlossaryEntry(term="Plunder", translation="Pilhar")
    mem_store.save_glossary([entry])
    initial_hash = entry.content_hash()

    art_dir = store.artifact_dir(series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)
    texts = UnitTexts(texts={"0": "Pilhar"}, used_terms={"Plunder": initial_hash})
    (art_dir / "translate_dialogue.json").write_text(texts.model_dump_json(), encoding="utf-8")

    manifests = ManifestSet(store, series, [ep])
    manifests.episodes[ep.key].stages["translate_dialogue"] = SimpleNamespace(
        status="done", key="k", artifact="translate_dialogue.json", artifact_hash="h"
    )
    manifests.save(ep)

    # Modifica o glossário
    updated_entry = GlossaryEntry(term="Plunder", translation="Saque")
    mem_store.save_glossary([updated_entry])

    runner = CliRunner()
    res = runner.invoke(app, ["--data-dir", str(data_dir), "retry", str(series_dir), "--stale"])
    assert res.exit_code == 0
    assert "1 episódio(s) desatualizado(s) reaberto(s)" in res.output

    reloaded_manifest = store.load_manifest(series.key, ep.key)
    assert "translate_dialogue" not in reloaded_manifest.stages
