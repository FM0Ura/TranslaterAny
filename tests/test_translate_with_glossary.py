from pathlib import Path
from types import SimpleNamespace

from translaterany.llm.fake import FakeLLM
from translaterany.memory.artifacts import ConsolidatedMemoryArtifact
from translaterany.memory.models import CharacterEntry, Gender, GlossaryCategory, GlossaryEntry
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.units import Episode, Series
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.subtitles.chunking import DialogueLine, format_batch_prompt
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit


def test_format_batch_prompt_includes_glossary_and_characters():
    lines = [DialogueLine(id="1", text="Hello from Hoshinoumi Academy!")]
    glossary = [
        GlossaryEntry(
            term="Hoshinoumi Academy",
            translation="Academia Hoshinoumi",
            category=GlossaryCategory.PLACE,
        )
    ]
    characters = [CharacterEntry(name="Yuu", gender=Gender.MALE, role="main", speech_style="informal")]

    prompt = format_batch_prompt(lines, [], glossary=glossary, characters=characters)
    assert "[GLOSSÁRIO OBRIGATÓRIO]" in prompt
    assert "Hoshinoumi Academy -> Academia Hoshinoumi" in prompt
    assert "[PERSONAGENS]" in prompt
    assert "Yuu (male): informal" in prompt


def test_translate_dialogue_filters_terms_and_populates_used_terms(tmp_path: Path):
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="0", style="Default", text="Welcome to Hoshinoumi Academy, Yuu!", markers=0, events=[0])],
    )
    classification = Classification(
        main_style="Default",
        units={"0": UnitClass(type="dialogue", uncertain=False, rule="test")},
        counts={"dialogue": 1},
        scenes=[],
    )
    cons_art = ConsolidatedMemoryArtifact(
        series_name="Charlotte",
        characters_count=1,
        glossary_count=2,
        characters_hash="h1",
        glossary_hash="h2",
        story_hash="h3",
        glossary_terms=["Hoshinoumi Academy", "Plunder"],
    )
    # Grava glossary.yaml e characters.yaml
    store = ArtifactStore(tmp_path / "data")
    series = Series(name="Charlotte (2015)", path=tmp_path)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    g_entry = GlossaryEntry(term="Hoshinoumi Academy", translation="Academia Hoshinoumi")
    from translaterany.memory.store import MemoryStore

    mem_store = MemoryStore(mem_dir)
    mem_store.save_glossary([g_entry, GlossaryEntry(term="Plunder", translation="Saque")])
    c_yuu = CharacterEntry(name="Yuu", gender=Gender.MALE, role="main", speech_style="informal")
    c_nao = CharacterEntry(name="Nao", gender=Gender.FEMALE, role="main", speech_style="direct")
    mem_store.save_characters([c_yuu, c_nao])

    captured = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name, model):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name == "consolidate_memory":
                return cons_art
            raise ValueError(name)

    # o termo do glossário chega ao modelo protegido por marcador
    fake_llm = FakeLLM(responses={"Welcome to ⟦G1⟧, Yuu!": "Bem-vindo à ⟦G1⟧, Yuu!"})
    stage = StageTranslateDialogue(client=fake_llm)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)
    ctx = SimpleNamespace(
        series=series,
        episode=ep,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=fake_llm,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.texts["0"] == "Bem-vindo à Academia Hoshinoumi, Yuu!"
    assert "Hoshinoumi Academy" in captured.used_terms
    assert "Plunder" not in captured.used_terms  # Plunder não foi mencionada no episódio

    # Verifica que personagem mencionado está no prompt e personagem não mencionado é excluído
    assert len(fake_llm.calls) > 0
    prompt_sent = fake_llm.calls[0].prompt
    assert "Yuu (male): informal" in prompt_sent
    assert "Nao" not in prompt_sent  # Nao não foi mencionada no episódio
