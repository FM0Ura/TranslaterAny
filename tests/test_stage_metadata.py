"""Testes para a etapa MetadataStage e configuração [metadata] no series.toml."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from translaterany.library.series_config import SeriesConfigError, load_series_config
from translaterany.memory.anilist import AniListMatch
from translaterany.memory.artifacts import MetadataArtifact
from translaterany.memory.models import CharacterEntry, EpisodeSynopsis, Gender
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.units import Series, SeriesConfig, SeriesMetadataConfig
from translaterany.stages.metadata import MetadataStage


def test_series_toml_with_metadata(tmp_path: Path) -> None:
    toml_file = tmp_path / "series.toml"
    toml_file.write_text("[metadata]\nanilist_id = 20954\n", encoding="utf-8")
    cfg = load_series_config(tmp_path)
    assert cfg.metadata.anilist_id == 20954


def test_series_toml_metadata_invalid_key(tmp_path: Path) -> None:
    toml_file = tmp_path / "series.toml"
    toml_file.write_text("[metadata]\nfoo = 123\n", encoding="utf-8")
    with pytest.raises(SeriesConfigError, match=r"\[metadata\] aceita apenas 'anilist_id'"):
        load_series_config(tmp_path)


def test_series_toml_metadata_invalid_id(tmp_path: Path) -> None:
    toml_file = tmp_path / "series.toml"
    toml_file.write_text('[metadata]\nanilist_id = "abc"\n', encoding="utf-8")
    with pytest.raises(SeriesConfigError, match=r"\[metadata\] anilist_id deve ser um número inteiro"):
        load_series_config(tmp_path)


def test_metadata_stage_runs_and_writes_artifact(tmp_path: Path) -> None:
    captured: MetadataArtifact | None = None

    class MockOutput:
        def json(self, obj: MetadataArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockAniList:
        def search_anime(self, title: str, year: int | None) -> AniListMatch | None:
            return AniListMatch(
                anilist_id=20954,
                mal_id=28999,
                title="Charlotte",
                romaji="Charlotte",
                year=2015,
                genres=["Drama"],
                characters=[CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE)],
            )

    class MockJikan:
        def get_episode_synopses(self, mal_id: int) -> dict[int, EpisodeSynopsis]:
            return {}

    stage = MetadataStage(anilist_client=MockAniList(), jikan_client=MockJikan())
    series = Series(name="Charlotte (2015)", path=tmp_path)
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        output=MockOutput(),
        inputs=SimpleNamespace(json=lambda *a: None),
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.matched is True
    assert captured.anilist_id == 20954
    assert len(captured.characters) == 1
    assert captured.title == "Charlotte"
    assert captured.story is not None
    assert captured.story.title == "Charlotte"


def test_metadata_stage_with_synopses(tmp_path: Path) -> None:
    captured: MetadataArtifact | None = None

    class MockOutput:
        def json(self, obj: MetadataArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockAniList:
        def search_anime(self, title: str, year: int | None) -> AniListMatch | None:
            return AniListMatch(
                anilist_id=20954,
                mal_id=28999,
                title="Charlotte",
                romaji="Charlotte",
                year=2015,
                genres=["Drama"],
                characters=[CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE)],
            )

    class MockJikan:
        def get_episode_synopses(self, mal_id: int) -> dict[int, EpisodeSynopsis]:
            return {
                1: EpisodeSynopsis(episode_key="EP1", number=1, title="I Think About Others", synopsis="Story 1"),
                2: EpisodeSynopsis(episode_key="EP2", number=2, title="Melody of Despair", synopsis="Story 2"),
            }

    stage = MetadataStage(anilist_client=MockAniList(), jikan_client=MockJikan())
    series = Series(name="Charlotte (2015)", path=tmp_path)
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        output=MockOutput(),
        inputs=SimpleNamespace(json=lambda *a: None),
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.matched is True
    assert captured.story is not None
    assert len(captured.story.episodes) == 2
    assert captured.story.episodes["EP1"].title == "I Think About Others"
    assert captured.story.episodes["EP2"].synopsis == "Story 2"


def test_metadata_stage_with_override_in_series_config(tmp_path: Path) -> None:
    captured: MetadataArtifact | None = None

    class MockOutput:
        def json(self, obj: MetadataArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockAniList:
        def search_anime(self, title: str, year: int | None) -> AniListMatch | None:
            return AniListMatch(
                anilist_id=99999,
                mal_id=28999,
                title="Charlotte",
                romaji="Charlotte",
                year=2015,
                genres=["Drama"],
                characters=[],
            )

    stage = MetadataStage(anilist_client=MockAniList(), jikan_client=None)
    config = SeriesConfig(metadata=SeriesMetadataConfig(anilist_id=20954))
    series = Series(name="Charlotte (2015)", path=tmp_path, config=config)
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        output=MockOutput(),
        inputs=SimpleNamespace(json=lambda *a: None),
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.matched is True
    # The override 20954 should take precedence over search result 99999
    assert captured.anilist_id == 20954


def test_metadata_stage_offline_fallback(tmp_path: Path) -> None:
    captured: MetadataArtifact | None = None

    class MockOutput:
        def json(self, obj: MetadataArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockAniListOffline:
        def search_anime(self, title: str, year: int | None) -> AniListMatch | None:
            return None

    stage = MetadataStage(anilist_client=MockAniListOffline(), jikan_client=None)
    series = Series(name="Serie Desconhecida", path=tmp_path)
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        output=MockOutput(),
        inputs=SimpleNamespace(json=lambda *a: None),
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.matched is False
    assert captured.anilist_id is None
    assert captured.title == "Serie Desconhecida"


def test_metadata_stage_registered() -> None:
    import translaterany.stages  # noqa: F401

    assert "metadata" in REGISTRY
    cls = REGISTRY.get("metadata")
    assert cls.name == "metadata"
    assert cls.scope.value == "series"
    assert cls.inputs == ("inventory",)
    assert cls.translates is False
