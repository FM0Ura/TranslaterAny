from pathlib import Path
from types import SimpleNamespace

from translaterany.llm.fake import FakeLLM
from translaterany.memory.artifacts import ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import EntrySource, GlossaryCategory
from translaterany.pipeline.stage import StageScope
from translaterany.pipeline.units import Episode
from translaterany.stages.extract_terms import ExtractTermsResponse, ExtractTermsStage
from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit


def test_extract_terms_stage_executes_and_outputs_artifact(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[
            Unit(id="0", style="Default", text="Welcome to Hoshinoumi Academy!", markers=0, events=[0]),
            Unit(id="1", style="Default", text="Use your Plunder ability.", markers=0, events=[1]),
        ],
    )
    meta = MetadataArtifact(matched=True, anilist_id=20954, title="Charlotte")

    captured: ExtractTermsArtifact | None = None

    class MockOutput:
        def json(self, obj: ExtractTermsArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "normalize":
                return doc
            if name == "metadata":
                return meta
            raise ValueError(name)

    fake_response = ExtractTermsResponse(
        terms=[
            {"term": "Hoshinoumi Academy", "translation": "Academia Hoshinoumi", "category": "place"},
            {"term": "Plunder", "translation": "Saque", "category": "technique"},
        ],
        character_mentions=["Yuu"],
    )
    fake_llm = FakeLLM([fake_response])
    stage = ExtractTermsStage(client=fake_llm)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)
    ctx = SimpleNamespace(
        episode=ep,
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.episode_key == "S01E01"
    assert len(captured.terms) == 2
    assert captured.terms[0].term == "Hoshinoumi Academy"
    assert captured.terms[0].translation == "Academia Hoshinoumi"
    assert captured.terms[0].category == GlossaryCategory.PLACE
    assert captured.terms[0].source == EntrySource.EXTRACTED
    assert captured.terms[1].term == "Plunder"
    assert captured.terms[1].translation == "Saque"
    assert captured.terms[1].category == GlossaryCategory.TECHNIQUE
    assert captured.terms[1].source == EntrySource.EXTRACTED
    assert captured.character_mentions == ["Yuu"]


def test_extract_terms_stage_properties() -> None:
    stage = ExtractTermsStage()
    assert stage.name == "extract_terms"
    assert stage.scope == StageScope.EPISODE
    assert stage.inputs == ("metadata", "normalize")
    assert stage.translates is False
    assert stage.enabled_by_default is True
    assert stage.options.model == "review"


def test_extract_terms_stage_empty_dialogue(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[],
    )
    captured: ExtractTermsArtifact | None = None

    class MockOutput:
        def json(self, obj: ExtractTermsArtifact) -> None:
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name: str, model: type) -> object:
            if name == "normalize":
                return doc
            if name == "metadata":
                return MetadataArtifact(matched=False, title="Empty")
            raise ValueError(name)

    fake_llm = FakeLLM([])
    stage = ExtractTermsStage(client=fake_llm)
    ep = Episode(key="S01E02", source=tmp_path / "S01E02.mkv", number=2, season=1)
    ctx = SimpleNamespace(
        episode=ep,
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.episode_key == "S01E02"
    assert len(captured.terms) == 0
    assert len(captured.character_mentions) == 0
    assert len(fake_llm.calls) == 0  # Nenhum chamada à IA se não houver falas


def test_extract_terms_category_normalization(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="0", style="Default", text="Some line", markers=0, events=[0])],
    )
    captured: ExtractTermsArtifact | None = None

    class MockOutput:
        def json(self, obj: ExtractTermsArtifact) -> None:
            nonlocal captured
            captured = obj

    fake_response = ExtractTermsResponse(
        terms=[
            {"term": "Syndicate", "translation": "Sindicato", "category": "org"},
            {"term": "Alliance", "translation": "Aliança", "category": "organization"},
            {"term": "UnknownItem", "translation": "Item", "category": "unexpected_cat"},
        ],
        character_mentions=[],
    )
    fake_llm = FakeLLM([fake_response])
    stage = ExtractTermsStage(client=fake_llm)
    ep = Episode(key="S01E03", source=tmp_path / "S01E03.mkv", number=3, season=1)
    ctx = SimpleNamespace(
        episode=ep,
        inputs=SimpleNamespace(
            json=lambda name, model: doc if name == "normalize" else MetadataArtifact(matched=False)
        ),
        output=MockOutput(),
        llm=fake_llm,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.terms[0].category == GlossaryCategory.ORGANIZATION
    assert captured.terms[1].category == GlossaryCategory.ORGANIZATION
    assert captured.terms[2].category == GlossaryCategory.GENERAL
