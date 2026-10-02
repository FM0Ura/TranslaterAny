"""Testes de armazenamento e precedência YAML com ruamel.yaml (MemoryStore)."""

from pathlib import Path

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
from translaterany.memory.store import MemoryStore


def test_yaml_roundtrip_glossary(tmp_path: Path):
    store = MemoryStore(tmp_path)
    entries = [
        GlossaryEntry(term="Academy", translation="Academia", category=GlossaryCategory.PLACE),
        GlossaryEntry(term="Power", translation="Poder", category=GlossaryCategory.GENERAL),
    ]
    h1 = store.save_glossary(entries)
    assert len(h1) == 64
    loaded = store.load_glossary()
    assert len(loaded) == 2
    assert loaded["Academy"].translation == "Academia"
    assert loaded["Power"].translation == "Poder"


def test_user_precedence_is_preserved_on_merge(tmp_path: Path):
    store = MemoryStore(tmp_path)
    user_entry = GlossaryEntry(
        term="Academy",
        translation="Colégio Especial",
        category=GlossaryCategory.PLACE,
        source=EntrySource.USER,
        notes="Decisão do fansub",
    )
    store.save_glossary([user_entry])

    ai_entry = GlossaryEntry(
        term="Academy",
        translation="Academia",
        category=GlossaryCategory.PLACE,
        source=EntrySource.EXTRACTED,
    )
    store.merge_glossary([ai_entry])

    reloaded = store.load_glossary()
    assert reloaded["Academy"].translation == "Colégio Especial"
    assert reloaded["Academy"].source == EntrySource.USER
    assert reloaded["Academy"].notes == "Decisão do fansub"


def test_character_merge_preserves_user_fields(tmp_path: Path):
    store = MemoryStore(tmp_path)
    c_user = CharacterEntry(name="Yuu", gender=Gender.MALE, role=CharacterRole.MAIN, source=EntrySource.USER)
    store.save_characters([c_user])

    c_meta = CharacterEntry(
        name="Yuu", gender=Gender.UNKNOWN, role=CharacterRole.SUPPORTING, source=EntrySource.METADATA
    )
    merged = store.merge_characters([c_meta])
    assert len(merged) == 1
    assert merged[0].role == CharacterRole.MAIN
    assert merged[0].gender == Gender.MALE


def test_story_save_and_load(tmp_path: Path):
    store = MemoryStore(tmp_path)
    assert store.load_story() is None

    story = StoryMemory(
        title="Charlotte",
        romaji_title="Charlotte",
        native_title="シャーロット",
        year=2015,
        synopsis="Adolescentes com poderes especiais em uma escola secreta.",
        genres=["Drama", "Supernatural"],
        tags=["School", "Superpowers"],
        episodes={
            "S01E01": EpisodeSynopsis(
                episode_key="S01E01",
                number=1,
                title="I Think About Others",
                synopsis="Yuu Otosaka usa sua habilidade.",
            )
        },
    )

    h = store.save_story(story)
    assert len(h) == 64
    assert (tmp_path / "story.yaml").exists()

    loaded = store.load_story()
    assert loaded is not None
    assert loaded.title == "Charlotte"
    assert loaded.year == 2015
    assert "S01E01" in loaded.episodes
    assert loaded.episodes["S01E01"].title == "I Think About Others"


def test_empty_or_missing_files(tmp_path: Path):
    store = MemoryStore(tmp_path)
    assert store.load_characters() == []
    assert store.load_glossary() == {}
    assert store.load_story() is None

    # Empty files created
    (tmp_path / "characters.yaml").write_text("", encoding="utf-8")
    (tmp_path / "glossary.yaml").write_text("", encoding="utf-8")
    (tmp_path / "story.yaml").write_text("", encoding="utf-8")

    assert store.load_characters() == []
    assert store.load_glossary() == {}
    assert store.load_story() is None


def test_save_glossary_accepts_dict(tmp_path: Path):
    store = MemoryStore(tmp_path)
    glossary_dict = {
        "Plunder": GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE),
    }
    h = store.save_glossary(glossary_dict)
    assert len(h) == 64

    loaded = store.load_glossary()
    assert "Plunder" in loaded
    assert loaded["Plunder"].translation == "Saque"


def test_full_source_precedence_hierarchy(tmp_path: Path):
    store = MemoryStore(tmp_path)

    # 1. Start with EXTRACTED entry
    extracted = GlossaryEntry(
        term="Telekinesis",
        translation="Telecinese",
        category=GlossaryCategory.TECHNIQUE,
        source=EntrySource.EXTRACTED,
    )
    store.save_glossary([extracted])

    # 2. Incoming EXTRACTED updates existing EXTRACTED (1 >= 1)
    extracted_v2 = GlossaryEntry(
        term="Telekinesis",
        translation="Telecinesia",
        category=GlossaryCategory.TECHNIQUE,
        source=EntrySource.EXTRACTED,
    )
    store.merge_glossary([extracted_v2])
    assert store.load_glossary()["Telekinesis"].translation == "Telecinesia"

    # 3. Incoming METADATA updates existing EXTRACTED (2 >= 1)
    meta = GlossaryEntry(
        term="Telekinesis",
        translation="Poder Mental",
        category=GlossaryCategory.TECHNIQUE,
        source=EntrySource.METADATA,
    )
    store.merge_glossary([meta])
    assert store.load_glossary()["Telekinesis"].translation == "Poder Mental"
    assert store.load_glossary()["Telekinesis"].source == EntrySource.METADATA

    # 4. Incoming EXTRACTED cannot overwrite METADATA (1 < 2)
    store.merge_glossary([extracted])
    assert store.load_glossary()["Telekinesis"].translation == "Poder Mental"
    assert store.load_glossary()["Telekinesis"].source == EntrySource.METADATA

    # 5. Incoming USER updates METADATA (3 >= 2)
    user = GlossaryEntry(
        term="Telekinesis",
        translation="Mover Objetos",
        category=GlossaryCategory.TECHNIQUE,
        source=EntrySource.USER,
        notes="Preferência pessoal",
    )
    store.merge_glossary([user])
    assert store.load_glossary()["Telekinesis"].translation == "Mover Objetos"
    assert store.load_glossary()["Telekinesis"].source == EntrySource.USER

    # 6. Incoming METADATA cannot overwrite USER (2 < 3)
    store.merge_glossary([meta])
    assert store.load_glossary()["Telekinesis"].translation == "Mover Objetos"
    assert store.load_glossary()["Telekinesis"].source == EntrySource.USER

    # 7. Another incoming USER never overwrites existing USER
    user_other = GlossaryEntry(
        term="Telekinesis",
        translation="Outra Tradução",
        category=GlossaryCategory.TECHNIQUE,
        source=EntrySource.USER,
    )
    store.merge_glossary([user_other])
    assert store.load_glossary()["Telekinesis"].translation == "Mover Objetos"
    assert store.load_glossary()["Telekinesis"].notes == "Preferência pessoal"


def test_merge_characters_preserves_order_and_appends_new(tmp_path: Path):
    store = MemoryStore(tmp_path)
    c1 = CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN, source=EntrySource.USER)
    c2 = CharacterEntry(name="Nao Tomori", gender=Gender.FEMALE, role=CharacterRole.MAIN, source=EntrySource.USER)
    store.save_characters([c1, c2])

    c3 = CharacterEntry(
        name="Ayumi Otosaka", gender=Gender.FEMALE, role=CharacterRole.SUPPORTING, source=EntrySource.METADATA
    )
    merged = store.merge_characters([c3])
    assert len(merged) == 3
    assert [c.name for c in merged] == ["Yuu Otosaka", "Nao Tomori", "Ayumi Otosaka"]

    reloaded = store.load_characters()
    assert len(reloaded) == 3
    assert [c.name for c in reloaded] == ["Yuu Otosaka", "Nao Tomori", "Ayumi Otosaka"]


def test_character_merge_preserves_non_empty_fields_when_updated(tmp_path: Path):
    store = MemoryStore(tmp_path)
    # Existing EXTRACTED with speech_style and aliases
    c_existing = CharacterEntry(
        name="Yuu",
        speech_style="sarcástico e direto",
        aliases=["Yuu-kun"],
        gender=Gender.MALE,
        source=EntrySource.EXTRACTED,
    )
    store.save_characters([c_existing])

    # Incoming METADATA with higher precedence, but missing speech_style and having new alias
    c_incoming = CharacterEntry(
        name="Yuu",
        native_name="乙坂 有宇",
        aliases=["Grim Reaper"],
        gender=Gender.MALE,
        role=CharacterRole.MAIN,
        speech_style=None,
        source=EntrySource.METADATA,
    )
    merged = store.merge_characters([c_incoming])
    assert len(merged) == 1
    char = merged[0]
    assert char.source == EntrySource.METADATA
    assert char.role == CharacterRole.MAIN
    assert char.native_name == "乙坂 有宇"
    # speech_style was preserved from existing
    assert char.speech_style == "sarcástico e direto"
    # aliases were merged without duplicates
    assert "Yuu-kun" in char.aliases
    assert "Grim Reaper" in char.aliases


def test_yaml_preserves_comments_on_merge(tmp_path: Path):
    yaml_content = """# Fichas de Personagens da Série
- name: Yuu # Protagonista principal
  gender: male
  role: main
  source: user

- name: Nao # Presidente do conselho
  gender: female
  role: main
  source: user
"""
    char_file = tmp_path / "characters.yaml"
    char_file.write_text(yaml_content, encoding="utf-8")

    store = MemoryStore(tmp_path)
    # Incoming metadata character and new character
    c_meta = CharacterEntry(name="Yuu", gender=Gender.MALE, role=CharacterRole.MAIN, source=EntrySource.METADATA)
    c_new = CharacterEntry(
        name="Ayumi", gender=Gender.FEMALE, role=CharacterRole.SUPPORTING, source=EntrySource.METADATA
    )

    store.merge_characters([c_meta, c_new])

    saved_text = char_file.read_text(encoding="utf-8")
    assert "# Fichas de Personagens da Série" in saved_text
    assert "# Protagonista principal" in saved_text
    assert "# Presidente do conselho" in saved_text
    assert "Ayumi" in saved_text


def test_yaml_preserves_comments_on_save(tmp_path: Path):
    glossary_content = """# Glossário Oficial Charlotte
- term: Academy # Termo oficial da escola
  translation: Academia
  category: place
  source: user

- term: Power # Conceito de poderes
  translation: Poder
  category: general
  source: extracted
"""
    gloss_file = tmp_path / "glossary.yaml"
    gloss_file.write_text(glossary_content, encoding="utf-8")

    store = MemoryStore(tmp_path)
    updated_entries = [
        GlossaryEntry(
            term="Academy",
            translation="Colégio Especial Hoshinoumi",
            category=GlossaryCategory.PLACE,
            source=EntrySource.USER,
            notes="Decisão do fansub",
        ),
        GlossaryEntry(
            term="Power",
            translation="Habilidade Especial",
            category=GlossaryCategory.GENERAL,
            source=EntrySource.EXTRACTED,
        ),
    ]

    store.save_glossary(updated_entries)

    saved_text = gloss_file.read_text(encoding="utf-8")
    assert "# Glossário Oficial Charlotte" in saved_text
    assert "# Termo oficial da escola" in saved_text
    assert "# Conceito de poderes" in saved_text
    assert "Colégio Especial Hoshinoumi" in saved_text
    assert "Habilidade Especial" in saved_text


def test_story_yaml_preserves_comments(tmp_path: Path):
    story_content = """# Memória Narrativa da Série
title: Charlotte # Título original
year: 2015
genres:
- Drama
episodes:
  S01E01: # Episódio Piloto
    episode_key: S01E01
    number: 1
    title: I Think About Others
"""
    story_file = tmp_path / "story.yaml"
    story_file.write_text(story_content, encoding="utf-8")

    store = MemoryStore(tmp_path)
    story = store.load_story()
    assert story is not None
    story.synopsis = "Jovens desenvolvem habilidades na puberdade."
    story.episodes["S01E01"].synopsis = "Yuu usa sua habilidade para trapacear."

    store.save_story(story)

    saved_text = story_file.read_text(encoding="utf-8")
    assert "# Memória Narrativa da Série" in saved_text
    assert "# Título original" in saved_text
    assert "# Episódio Piloto" in saved_text
    assert "Jovens desenvolvem habilidades" in saved_text


def test_merge_characters_reversed_name_order_and_gender_inheritance(tmp_path: Path):
    store = MemoryStore(tmp_path)
    # 1. Existing extracted character with Eastern name order and unknown gender
    c1 = CharacterEntry(name="Hyoudou Issei", gender=Gender.UNKNOWN, aliases=["Issei"], source=EntrySource.EXTRACTED)
    store.save_characters([c1])

    # 2. Incoming metadata character with Western name order and known male gender
    c2 = CharacterEntry(
        name="Issei Hyoudou",
        gender=Gender.MALE,
        role=CharacterRole.MAIN,
        source=EntrySource.METADATA,
    )
    merged = store.merge_characters([c2])

    assert len(merged) == 1
    assert merged[0].gender == Gender.MALE
    assert "Issei" in merged[0].aliases
    assert ("Hyoudou Issei" in merged[0].aliases) or (merged[0].name == "Hyoudou Issei")

