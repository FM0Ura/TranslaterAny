from translaterany.memory.artifacts import (
    ConsolidatedMemoryArtifact,
    ExtractTermsArtifact,
    MetadataArtifact,
)
from translaterany.memory.models import (
    CharacterEntry,
    CharacterRole,
    EntrySource,
    EpisodeSynopsis,
    Gender,
    GlossaryCategory,
    GlossaryEntry,
    StoryMemory,
)


def test_glossary_entry_content_hash():
    entry1 = GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)
    entry2 = GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)
    assert entry1.content_hash() == entry2.content_hash()

    entry3 = GlossaryEntry(term="Plunder", translation="Pilhar", category=GlossaryCategory.TECHNIQUE)
    assert entry1.content_hash() != entry3.content_hash()

    entry_pipe1 = GlossaryEntry(term="a|b", translation="c")
    entry_pipe2 = GlossaryEntry(term="a", translation="b|c")
    assert entry_pipe1.content_hash() != entry_pipe2.content_hash()


def test_character_entry_defaults():
    char = CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN)
    assert char.source == EntrySource.EXTRACTED
    assert char.aliases == []


def test_story_memory_episode_key():
    story = StoryMemory(title="Charlotte", year=2015)
    story.episodes["S01E01"] = EpisodeSynopsis(episode_key="S01E01", number=1, synopsis="Primeiro ep")
    assert "S01E01" in story.episodes
    assert story.episodes["S01E01"].number == 1


def test_artifacts_serialization():
    meta = MetadataArtifact(matched=True, anilist_id=20954, title="Charlotte")
    data = meta.model_dump_json()
    loaded = MetadataArtifact.model_validate_json(data)
    assert loaded.anilist_id == 20954
    assert loaded.matched is True

    consolidated = ConsolidatedMemoryArtifact(
        series_name="Charlotte",
        characters_count=4,
        glossary_count=12,
        characters_hash="abc",
        glossary_hash="def",
        story_hash="123",
        glossary_terms=["Plunder", "Collapse"],
    )
    c_data = consolidated.model_dump_json()
    assert ConsolidatedMemoryArtifact.model_validate_json(c_data).glossary_count == 12


def test_extract_terms_artifact():
    term = GlossaryEntry(term="Collapse", translation="Colapso", category=GlossaryCategory.TECHNIQUE)
    artifact = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[term],
        character_mentions=["Yuu Otosaka"],
    )
    data = artifact.model_dump_json()
    loaded = ExtractTermsArtifact.model_validate_json(data)
    assert loaded.episode_key == "S01E01"
    assert len(loaded.terms) == 1
    assert loaded.terms[0].term == "Collapse"
    assert loaded.character_mentions == ["Yuu Otosaka"]


def test_memory_exports():
    import translaterany.memory as mem

    assert hasattr(mem, "CharacterEntry")
    assert hasattr(mem, "CharacterRole")
    assert hasattr(mem, "EntrySource")
    assert hasattr(mem, "Gender")
    assert hasattr(mem, "GlossaryCategory")
    assert hasattr(mem, "GlossaryEntry")
    assert hasattr(mem, "StoryMemory")
    assert hasattr(mem, "EpisodeSynopsis")
    assert hasattr(mem, "MetadataArtifact")
    assert hasattr(mem, "ExtractTermsArtifact")
    assert hasattr(mem, "ConsolidatedMemoryArtifact")
