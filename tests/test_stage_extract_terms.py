from pathlib import Path
from types import SimpleNamespace

import pytest

from translaterany.llm.client import LLMTransientError
from translaterany.llm.fake import FakeLLM
from translaterany.memory.artifacts import ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import EntrySource, GlossaryCategory
from translaterany.pipeline.stage import StageScope
from translaterany.pipeline.units import Episode
from translaterany.stages.extract_terms import ExtractTermsOptions, ExtractTermsResponse, ExtractTermsStage
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


def test_extract_terms_error_bubbles_up(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="0", style="Default", text="Hello", markers=0, events=[0])],
    )
    fake_llm = FakeLLM([LLMTransientError("API network timeout")])
    stage = ExtractTermsStage(client=fake_llm)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)
    ctx = SimpleNamespace(
        episode=ep,
        inputs=SimpleNamespace(
            json=lambda name, model: doc if name == "normalize" else MetadataArtifact(matched=False)
        ),
        output=SimpleNamespace(json=lambda obj: None),
        llm=fake_llm,
    )
    with pytest.raises(LLMTransientError, match="API network timeout"):
        stage.run(ctx)


def test_extract_terms_fallback_model_success(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="0", style="Default", text="Hello", markers=0, events=[0])],
    )
    fallback_resp = ExtractTermsResponse(
        terms=[{"term": "Power", "translation": "Poder", "category": "technique"}],
        character_mentions=[],
    )
    # Primeiro erro, segunda chamada tem sucesso
    fake_llm = FakeLLM([LLMTransientError("Primary failed"), fallback_resp])
    options = ExtractTermsOptions(model="review", fallback_model="gemma4")
    stage = ExtractTermsStage(client=fake_llm, options=options)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)

    captured: ExtractTermsArtifact | None = None

    class MockOutput:
        def json(self, obj: ExtractTermsArtifact) -> None:
            nonlocal captured
            captured = obj

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
    assert len(captured.terms) == 1
    assert captured.terms[0].term == "Power"
    assert len(fake_llm.calls) == 2
    assert fake_llm.calls[0].model == "review"
    assert fake_llm.calls[1].model == "gemma4"


def test_extract_terms_max_sample_lines(tmp_path: Path) -> None:
    units = [Unit(id=str(i), style="Default", text=f"Line {i}", markers=0, events=[i]) for i in range(350)]
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=units,
    )
    fake_resp = ExtractTermsResponse(terms=[], character_mentions=[])
    fake_llm = FakeLLM([fake_resp])
    # Padrão: max_sample_lines=500 deve incluir todas as 350 falas
    stage = ExtractTermsStage(client=fake_llm)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)
    ctx = SimpleNamespace(
        episode=ep,
        inputs=SimpleNamespace(
            json=lambda name, model: doc if name == "normalize" else MetadataArtifact(matched=False)
        ),
        output=SimpleNamespace(json=lambda obj: None),
        llm=fake_llm,
    )
    stage.run(ctx)
    assert len(fake_llm.calls) == 1
    prompt = fake_llm.calls[0].prompt
    assert "- Line 0" in prompt
    assert "- Line 349" in prompt

    # Com limite explícito de 50 falas:
    fake_llm_50 = FakeLLM([fake_resp])
    stage_50 = ExtractTermsStage(client=fake_llm_50, options=ExtractTermsOptions(max_sample_lines=50))
    ctx.llm = fake_llm_50
    stage_50.run(ctx)
    assert len(fake_llm_50.calls) == 1
    prompt_50 = fake_llm_50.calls[0].prompt
    assert "- Line 0" in prompt_50
    assert "- Line 49" in prompt_50
    assert "- Line 50" not in prompt_50
