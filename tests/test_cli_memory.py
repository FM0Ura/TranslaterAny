"""Testes para o comando CLI memory."""

from pathlib import Path

from typer.testing import CliRunner

from translaterany.cli.app import app
from translaterany.memory.models import (
    CharacterEntry,
    CharacterRole,
    EntrySource,
    Gender,
    GlossaryCategory,
    GlossaryEntry,
    StoryMemory,
)
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.units import Series

runner = CliRunner()


def test_memory_command_help():
    result = runner.invoke(app, ["memory", "--help"])
    assert result.exit_code == 0
    assert "memória da série" in result.output.lower()


def test_memory_command_displays_glossary_table(tmp_path: Path):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    MemoryStore(mem_dir).save_glossary([
        GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)
    ])

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir)])
    assert result.exit_code == 0
    assert "Plunder" in result.output
    assert "Saque" in result.output


def test_memory_command_displays_characters_and_story(tmp_path: Path):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_store = MemoryStore(mem_dir)
    mem_store.save_characters([
        CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN, speech_style="informal")
    ])
    mem_store.save_story(StoryMemory(title="Charlotte", synopsis="Adolescentes com habilidades especiais."))

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir)])
    assert result.exit_code == 0
    assert "Yuu Otosaka" in result.output
    assert "informal" in result.output
    assert "Adolescentes com habilidades" in result.output


def test_memory_command_export(tmp_path: Path):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_store = MemoryStore(mem_dir)
    mem_store.save_glossary([GlossaryEntry(term="Plunder", translation="Saque")])
    mem_store.save_characters([CharacterEntry(name="Yuu Otosaka")])
    mem_store.save_story(StoryMemory(title="Charlotte"))

    export_dir = tmp_path / "exported_memory"

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--export", str(export_dir)])
    assert result.exit_code == 0
    assert (export_dir / "glossary.yaml").exists()
    assert (export_dir / "characters.yaml").exists()
    assert (export_dir / "story.yaml").exists()


def test_memory_command_import(tmp_path: Path):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_store = MemoryStore(mem_dir)
    mem_store.save_glossary([GlossaryEntry(term="Plunder", translation="Pilhar", source=EntrySource.EXTRACTED)])

    import_file = tmp_path / "new_terms.yaml"
    import_file.write_text(
        "- term: Plunder\n  translation: Saque\n  category: technique\n"
        "- term: Collapse\n  translation: Desmoronar\n  category: technique\n",
        encoding="utf-8",
    )

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--import", str(import_file)])
    assert result.exit_code == 0
    reloaded_glossary = mem_store.load_glossary()
    assert reloaded_glossary["Plunder"].translation == "Saque"
    assert reloaded_glossary["Plunder"].source == EntrySource.USER
    assert "Collapse" in reloaded_glossary


def test_memory_command_refresh(tmp_path: Path, monkeypatch):
    import httpx

    mock_anilist = {
        "data": {
            "Media": {
                "id": 20954,
                "idMal": 28999,
                "title": {"romaji": "Charlotte", "english": "Charlotte", "native": "シャーロット"},
                "seasonYear": 2015,
                "episodes": 1,
                "genres": ["Supernatural"],
                "characters": {"edges": []},
            }
        }
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, json=mock_anilist))
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json={"data": []}))

    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--refresh"])
    assert result.exit_code == 0
    assert "atualizados com sucesso" in result.output.lower()
