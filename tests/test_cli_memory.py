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
    MemoryStore(mem_dir).save_glossary(
        [GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)]
    )

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
    mem_store.save_characters(
        [CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN, speech_style="informal")]
    )
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


def test_memory_command_refresh_preserves_other_series_cache(tmp_path: Path, monkeypatch):
    import hashlib

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

    data_dir = tmp_path / "data"
    cache_anilist = data_dir / "cache" / "anilist"
    cache_jikan = data_dir / "cache" / "jikan"
    cache_anilist.mkdir(parents=True, exist_ok=True)
    cache_jikan.mkdir(parents=True, exist_ok=True)

    # Cache de OUTRA série que NÃO deve ser apagado
    other_anilist = cache_anilist / "other_series_hash.json"
    other_anilist.write_text('{"title": "Other Series"}', encoding="utf-8")
    other_jikan = cache_jikan / "99999_episodes.json"
    other_jikan.write_text('[{"number": 1}]', encoding="utf-8")

    # Cache da série atual
    norm_key = "charlotte::2015"
    charlotte_hash = hashlib.sha256(norm_key.encode("utf-8")).hexdigest()[:16]
    charlotte_anilist = cache_anilist / f"{charlotte_hash}.json"
    charlotte_anilist.write_text('{"idMal": 28999}', encoding="utf-8")
    charlotte_jikan = cache_jikan / "28999_episodes.json"
    charlotte_jikan.write_text('[{"number": 1, "synopsis": "Old"}]', encoding="utf-8")

    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--refresh"])
    assert result.exit_code == 0
    assert "atualizados com sucesso" in result.output.lower()

    # Verifica que o cache da outra série permanece intacto
    assert other_anilist.exists()
    assert other_jikan.exists()


def test_memory_command_import_compound_yaml(tmp_path: Path):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_store = MemoryStore(mem_dir)

    compound_file = tmp_path / "compound.yaml"
    compound_file.write_text(
        "glossary:\n"
        "  - term: Plunder\n"
        "    translation: Saque\n"
        "    category: technique\n"
        "characters:\n"
        "  - name: Nao Tomori\n"
        "    gender: female\n"
        "    role: main\n",
        encoding="utf-8",
    )

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--import", str(compound_file)])
    assert result.exit_code == 0
    assert "1 termo(s)" in result.output
    assert "1 personagem(ns)" in result.output

    glossary = mem_store.load_glossary()
    characters = mem_store.load_characters()
    assert "Plunder" in glossary
    assert glossary["Plunder"].translation == "Saque"
    assert any(c.name == "Nao Tomori" for c in characters)


def test_memory_command_refresh_with_override_id(tmp_path: Path, monkeypatch):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    (series_dir / "series.toml").write_text("[metadata]\nanilist_id = 99999\n", encoding="utf-8")

    called_with_id = None

    class MockAniListClient:
        def __init__(self, cache_dir):
            pass

        def get_anime_by_id(self, anilist_id: int):
            nonlocal called_with_id
            called_with_id = anilist_id
            from translaterany.memory.anilist import AniListMatch

            return AniListMatch(anilist_id=anilist_id, title="Overridden Anime", romaji="Overridden")

        def search_anime(self, title: str, year: int | None = None):
            raise AssertionError("search_anime não deveria ser chamado quando get_anime_by_id tem sucesso")

    monkeypatch.setattr("translaterany.memory.anilist.AniListClient", MockAniListClient)

    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--refresh"])
    assert result.exit_code == 0
    assert called_with_id == 99999
    assert "atualizados com sucesso" in result.output.lower()


def test_memory_command_refresh_not_found(tmp_path: Path, monkeypatch):
    class MockAniListClient:
        def __init__(self, cache_dir):
            pass

        def search_anime(self, title: str, year: int | None = None):
            return None

    monkeypatch.setattr("translaterany.memory.anilist.AniListClient", MockAniListClient)

    series_dir = tmp_path / "Desconhecido (2099)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--refresh"])
    assert result.exit_code == 0
    assert "nenhum metadado encontrado" in result.output.lower()


def test_memory_command_refresh_preserves_existing_synopsis(tmp_path: Path, monkeypatch):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_store = MemoryStore(mem_dir)
    mem_store.save_story(StoryMemory(title="Charlotte", synopsis="Sinopse existente de teste."))

    class MockAniListClient:
        def __init__(self, cache_dir):
            pass

        def search_anime(self, title: str, year: int | None = None):
            from translaterany.memory.anilist import AniListMatch

            return AniListMatch(anilist_id=20954, title="Charlotte", romaji="Charlotte")

    monkeypatch.setattr("translaterany.memory.anilist.AniListClient", MockAniListClient)

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--refresh"])
    assert result.exit_code == 0

    reloaded_story = mem_store.load_story()
    assert reloaded_story is not None
    assert reloaded_story.synopsis == "Sinopse existente de teste."


def test_memory_command_refresh_with_override_id_not_found_does_not_fallback(tmp_path: Path, monkeypatch):
    class MockAniListClient:
        def __init__(self, cache_dir):
            pass

        def get_anime_by_id(self, anilist_id: int):
            return None

        def search_anime(self, title: str, year: int | None = None):
            raise AssertionError("search_anime não deveria ser chamado quando override_id está configurado!")

    monkeypatch.setattr("translaterany.memory.anilist.AniListClient", MockAniListClient)

    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    (series_dir / "series.toml").write_text("[metadata]\nanilist_id = 12345\n", encoding="utf-8")

    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir), "--refresh"])
    assert result.exit_code == 0
    assert "nenhum metadado encontrado" in result.output.lower()
