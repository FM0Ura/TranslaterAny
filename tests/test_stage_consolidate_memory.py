from pathlib import Path
from types import SimpleNamespace

from translaterany.memory.artifacts import ConsolidatedMemoryArtifact, ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import CharacterEntry, EntrySource, Gender, GlossaryCategory, GlossaryEntry
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.stage import StageScope
from translaterany.pipeline.units import Series
from translaterany.stages.consolidate_memory import ConsolidateMemoryStage


def test_consolidate_memory_stage_produces_yamls_and_artifact(tmp_path: Path) -> None:
    meta = MetadataArtifact(
        matched=True,
        anilist_id=20954,
        title="Charlotte",
        characters=[CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE)],
    )
    ep1_terms = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)],
        character_mentions=["Yuu"],
    )

    captured: ConsolidatedMemoryArtifact | None = None

    class MockOutput:
        def json(self, obj: ConsolidatedMemoryArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "metadata":
                return meta
            raise ValueError(name)

        def json_all(self, name: str, model: type) -> dict[str, ExtractTermsArtifact]:
            if name == "extract_terms":
                return {"S01E01": ep1_terms}
            raise ValueError(name)

    series = Series(name="Charlotte (2015)", path=tmp_path)
    store = ArtifactStore(tmp_path / "data")
    stage = ConsolidateMemoryStage()
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=None,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.series_name == "Charlotte (2015)"
    assert captured.glossary_count == 1
    assert captured.characters_count == 1
    assert "Plunder" in captured.glossary_terms
    assert len(captured.characters_hash) == 64
    assert len(captured.glossary_hash) == 64
    assert len(captured.story_hash) == 64

    # Verifica que os arquivos YAML foram gravados em data_dir/series/<key>/memory/
    mem_dir = store.series_dir(series.key) / "memory"
    assert (mem_dir / "glossary.yaml").exists()
    assert (mem_dir / "characters.yaml").exists()
    assert (mem_dir / "story.yaml").exists()


def test_consolidate_memory_stage_properties() -> None:
    stage = ConsolidateMemoryStage()
    assert stage.name == "consolidate_memory"
    assert stage.scope == StageScope.SERIES
    assert stage.inputs == ("metadata", "extract_terms")
    assert stage.translates is False
    assert stage.enabled_by_default is True


def test_consolidate_memory_preserves_user_entries(tmp_path: Path) -> None:
    from translaterany.memory.store import MemoryStore

    series = Series(name="Charlotte (2015)", path=tmp_path)
    store = ArtifactStore(tmp_path / "data")
    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)

    # Pré-cria entrada manual de usuário
    mem_store.save_glossary(
        [
            GlossaryEntry(
                term="Plunder",
                translation="Roubo Divino",  # Tradução personalizada do usuário
                category=GlossaryCategory.TECHNIQUE,
                source=EntrySource.USER,
            )
        ]
    )

    meta = MetadataArtifact(matched=True, anilist_id=20954, title="Charlotte")
    ep1_terms = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)],
        character_mentions=[],
    )

    captured: ConsolidatedMemoryArtifact | None = None

    class MockOutput:
        def json(self, obj: ConsolidatedMemoryArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "metadata":
                return meta
            raise ValueError(name)

        def json_all(self, name: str, model: type) -> dict[str, ExtractTermsArtifact]:
            if name == "extract_terms":
                return {"S01E01": ep1_terms}
            raise ValueError(name)

    stage = ConsolidateMemoryStage()
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=None,
    )
    stage.run(ctx)

    # Carrega e verifica que a tradução do usuário foi estritamente preservada
    loaded_glossary = mem_store.load_glossary()
    assert loaded_glossary["Plunder"].translation == "Roubo Divino"
    assert loaded_glossary["Plunder"].source == EntrySource.USER


def test_consolidate_memory_multiple_episodes_and_new_characters(tmp_path: Path) -> None:
    from translaterany.memory.store import MemoryStore

    series = Series(name="Charlotte (2015)", path=tmp_path)
    store = ArtifactStore(tmp_path / "data")

    meta = MetadataArtifact(
        matched=True,
        anilist_id=20954,
        title="Charlotte",
        characters=[CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE)],
    )
    ep1 = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)],
        character_mentions=["Yuu"],
    )
    ep2 = ExtractTermsArtifact(
        episode_key="S01E02",
        terms=[GlossaryEntry(term="Collapse", translation="Colapso", category=GlossaryCategory.TECHNIQUE)],
        character_mentions=["Ayumi Otosaka"],  # Novo personagem mencionado
    )

    class MockOutput:
        def json(self, obj: ConsolidatedMemoryArtifact) -> None:
            pass

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "metadata":
                return meta
            raise ValueError(name)

        def json_all(self, name: str, model: type) -> dict[str, ExtractTermsArtifact]:
            if name == "extract_terms":
                return {"S01E01": ep1, "S01E02": ep2}
            raise ValueError(name)

    stage = ConsolidateMemoryStage()
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=None,
    )
    stage.run(ctx)

    mem_store = MemoryStore(store.series_dir(series.key) / "memory")
    chars = mem_store.load_characters()
    glossary = mem_store.load_glossary()

    assert len(chars) == 2
    char_names = {c.name for c in chars}
    assert "Yuu Otosaka" in char_names
    assert "Ayumi Otosaka" in char_names

    assert len(glossary) == 2
    assert "Plunder" in glossary
    assert "Collapse" in glossary


def test_consolidate_memory_ignores_short_tokens_and_honorifics(tmp_path: Path) -> None:
    from translaterany.memory.store import MemoryStore

    series = Series(name="Dr. Stone (2019)", path=tmp_path)
    store = ArtifactStore(tmp_path / "data")

    meta = MetadataArtifact(
        matched=True,
        anilist_id=105333,
        title="Dr. Stone",
        characters=[CharacterEntry(name="Senku Ishigami", gender=Gender.MALE)],
    )
    # Menções:
    # - "Ishigami": token válido (> 2 chars, não honorífico) -> deve ser adicionado aos aliases de Senku
    # - "san": honorífico comum -> NÃO deve ser adicionado aos aliases e NÃO deve virar novo personagem
    # - "yo": token curto (<= 2 chars) -> NÃO deve virar novo personagem
    # - "kun": honorífico -> NÃO deve virar novo personagem
    # - "Taiju Oki": personagem novo válido -> deve ser registrado
    ep1 = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[],
        character_mentions=["Ishigami", "san", "yo", "kun", "Taiju Oki"],
    )

    class MockOutput:
        def json(self, obj: ConsolidatedMemoryArtifact) -> None:
            pass

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "metadata":
                return meta
            raise ValueError(name)

        def json_all(self, name: str, model: type) -> dict[str, ExtractTermsArtifact]:
            if name == "extract_terms":
                return {"S01E01": ep1}
            raise ValueError(name)

    stage = ConsolidateMemoryStage()
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=None,
    )
    stage.run(ctx)

    mem_store = MemoryStore(store.series_dir(series.key) / "memory")
    chars = mem_store.load_characters()

    char_names = {c.name for c in chars}
    assert "Senku Ishigami" in char_names
    assert "Taiju Oki" in char_names
    # "san", "yo", "kun" não devem virar personagens
    assert "san" not in char_names
    assert "yo" not in char_names
    assert "kun" not in char_names

    # Senku deve ter recebido "Ishigami" como alias, mas não os honoríficos/curtos
    senku = next(c for c in chars if c.name == "Senku Ishigami")
    assert "Ishigami" in senku.aliases
    assert "san" not in senku.aliases
    assert "yo" not in senku.aliases
    assert "kun" not in senku.aliases


def _run_consolidate(tmp_path: Path, meta: MetadataArtifact, episodes: dict[str, ExtractTermsArtifact]):
    from translaterany.memory.store import MemoryStore

    series = Series(name="Synthetic Series (2020)", path=tmp_path)
    store = ArtifactStore(tmp_path / "data")

    class MockOutput:
        def json(self, obj: ConsolidatedMemoryArtifact) -> None:
            pass

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "metadata":
                return meta
            raise ValueError(name)

        def json_all(self, name: str, model: type) -> dict[str, ExtractTermsArtifact]:
            if name == "extract_terms":
                return episodes
            raise ValueError(name)

    ctx = SimpleNamespace(series=series, episode=None, inputs=MockInputs(), output=MockOutput(), store=store, llm=None)
    ConsolidateMemoryStage().run(ctx)
    return MemoryStore(store.series_dir(series.key) / "memory")


def test_consolidate_memory_sanitizes_glossary_aliases_and_is_idempotent(tmp_path: Path) -> None:
    meta = MetadataArtifact(
        matched=True,
        title="Synthetic",
        characters=[CharacterEntry(name="Rin Okada", aliases=["Rinrin"], gender=Gender.FEMALE)],
    )
    cat = GlossaryCategory.NAME
    ep = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[
            GlossaryEntry(
                term="Phantom Rin",
                translation="Phantom Rin",
                category=cat,
                keep_original=True,
                aliases=["Phantom Rin", "Rinrin", "Phantom"],
            ),
            GlossaryEntry(term="Rinrin", translation="Rinrin", category=cat, keep_original=True),
            GlossaryEntry(term="Gadget", translation="Gadget", category=GlossaryCategory.OBJECT),
            GlossaryEntry(
                term="Gadget (draft name)", translation="Gadget (rascunho)", category=GlossaryCategory.OBJECT
            ),
        ],
    )
    mem = _run_consolidate(tmp_path, meta, {"S01E01": ep})
    glossary = mem.load_glossary()
    assert glossary["Phantom Rin"].aliases == ["Phantom"]
    assert "Gadget (draft name)" not in glossary
    assert glossary["Gadget"].aliases == ["Gadget (draft name)"]
    first = mem.glossary_path.read_text(encoding="utf-8")

    mem = _run_consolidate(tmp_path, meta, {"S01E01": ep})
    assert mem.glossary_path.read_text(encoding="utf-8") == first


def test_consolidate_memory_merges_character_styles_across_episodes(tmp_path: Path) -> None:
    from translaterany.memory.artifacts import CharacterStyle

    meta = MetadataArtifact(
        matched=True,
        title="Synthetic",
        characters=[
            CharacterEntry(name="Rin Okada", gender=Gender.FEMALE),
            CharacterEntry(name="Taro Sato", speech_style="estilo da metadata"),
        ],
    )
    ep1 = ExtractTermsArtifact(
        episode_key="S01E01",
        character_styles=[
            CharacterStyle(name="Rin Okada", speech_style="fala rápido, gírias"),
            CharacterStyle(name="Taro Sato", speech_style="estilo novo"),
            CharacterStyle(name="Mika", speech_style="meiga"),
        ],
    )
    ep2 = ExtractTermsArtifact(
        episode_key="S01E02",
        character_styles=[CharacterStyle(name="Rin", speech_style="fala rápido, gírias")],
    )
    old_ep = ExtractTermsArtifact.model_validate({"episode_key": "S01E03", "terms": [], "character_mentions": []})
    mem = _run_consolidate(tmp_path, meta, {"S01E01": ep1, "S01E02": ep2, "S01E03": old_ep})

    chars = {c.name: c for c in mem.load_characters()}
    assert chars["Rin Okada"].speech_style == "fala rápido, gírias"
    assert chars["Rin Okada"].source == EntrySource.METADATA
    assert chars["Taro Sato"].speech_style == "estilo da metadata"
    assert chars["Mika"].speech_style == "meiga"
    assert chars["Mika"].source == EntrySource.EXTRACTED

    # reexecutar não altera nada e uma segunda rodada sem estilos não apaga os já salvos
    first = mem.characters_path.read_text(encoding="utf-8")
    mem = _run_consolidate(tmp_path, meta, {"S01E01": ep1, "S01E02": ep2, "S01E03": old_ep})
    assert mem.characters_path.read_text(encoding="utf-8") == first
    mem = _run_consolidate(tmp_path, meta, {"S01E03": old_ep})
    assert {c.name: c for c in mem.load_characters()}["Rin Okada"].speech_style == "fala rápido, gírias"


def test_consolidate_memory_resolves_nicknames_instead_of_creating_characters(tmp_path: Path) -> None:
    from translaterany.memory.artifacts import CharacterStyle

    meta = MetadataArtifact(
        matched=True,
        title="Synthetic",
        characters=[
            CharacterEntry(name="Luka Urushibara", aliases=["Luka"]),
            CharacterEntry(name="Ren Aoki", aliases=["Super Ren"]),
        ],
    )
    ep = ExtractTermsArtifact(
        episode_key="S01E01",
        character_mentions=["Luka Urushibara", "Ren Aoki", "Lukako", "Super Ren", "Zanzibar"],
        character_styles=[
            CharacterStyle(name="Rukako", speech_style="doce"),
            CharacterStyle(name="Ren-kun", speech_style="seco"),
        ],
    )
    mem = _run_consolidate(tmp_path, meta, {"S01E01": ep})
    chars = {c.name: c for c in mem.load_characters()}
    assert set(chars) == {"Luka Urushibara", "Ren Aoki", "Zanzibar"}
    assert chars["Luka Urushibara"].aliases == ["Luka", "Lukako", "Rukako"]
    assert chars["Luka Urushibara"].speech_style == "doce"
    assert chars["Ren Aoki"].speech_style == "seco"
    assert chars["Zanzibar"].source == EntrySource.EXTRACTED

    first = mem.characters_path.read_text(encoding="utf-8")
    mem = _run_consolidate(tmp_path, meta, {"S01E01": ep})
    assert mem.characters_path.read_text(encoding="utf-8") == first


def test_consolidate_memory_heals_stale_extracted_nickname_characters(tmp_path: Path) -> None:
    from translaterany.memory.store import MemoryStore

    meta = MetadataArtifact(
        matched=True,
        title="Synthetic",
        characters=[CharacterEntry(name="Luka Urushibara"), CharacterEntry(name="Ren Aoki")],
    )
    series = Series(name="Synthetic Series (2020)", path=tmp_path)
    mem_dir = ArtifactStore(tmp_path / "data").series_dir(series.key) / "memory"
    MemoryStore(mem_dir).save_characters(
        [
            CharacterEntry(name="Rukako", source=EntrySource.EXTRACTED),
            CharacterEntry(name="Zanzibar", source=EntrySource.EXTRACTED),
            CharacterEntry(name="Ren Aoki, Luka Urushibara", source=EntrySource.EXTRACTED),
        ]
    )
    mem = _run_consolidate(tmp_path, meta, {})
    chars = {c.name: c for c in mem.load_characters()}
    assert set(chars) == {"Luka Urushibara", "Ren Aoki", "Zanzibar"}
    assert chars["Luka Urushibara"].aliases == ["Rukako"]

    first = mem.characters_path.read_text(encoding="utf-8")
    mem = _run_consolidate(tmp_path, meta, {})
    assert mem.characters_path.read_text(encoding="utf-8") == first
