from pathlib import Path

from mkvtools import needs_mkvtoolnix

from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage import StageScope
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.subtitles.classify import ClassifiedUnit, ClassifiedUnitCollection


def test_translate_dialogue_preserves_inline_tags(tmp_path: Path) -> None:
    # Unidade com tags de formatação ASS
    unit = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text=r"{\an8}Hello {\b1}world{\b0}!",
        clean_text="Hello world!",
        prefix=r"{\an8}",
        suffix="",
        start_ms=1000,
        end_ms=2500,
        style="Default",
    )
    collection = ClassifiedUnitCollection(units=[unit])

    # FakeLLM devolvendo tradução simples
    fake_llm = FakeLLM(responses={"Hello world!": "Olá mundo!"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated_collection = stage.translate_collection(collection)
    res_unit = translated_collection.units[0]
    assert res_unit.clean_text == "Olá mundo!"
    assert r"{\an8}" in res_unit.raw_text
    assert res_unit.start_ms == 1000
    assert res_unit.end_ms == 2500


def test_translate_dialogue_ignores_non_dialogue_units() -> None:
    u_dialogue = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text="Hello",
        clean_text="Hello",
        prefix="",
        suffix="",
        start_ms=1000,
        end_ms=2000,
        style="Default",
    )
    u_sign = ClassifiedUnit(
        id="u2",
        line_type="sign",
        raw_text="Tokyo Station",
        clean_text="Tokyo Station",
        prefix="",
        suffix="",
        start_ms=1000,
        end_ms=2000,
        style="Sign",
    )
    collection = ClassifiedUnitCollection(units=[u_dialogue, u_sign])

    fake_llm = FakeLLM(responses={"Hello": "Olá"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated = stage.translate_collection(collection)
    assert translated.units[0].clean_text == "Olá"
    assert translated.units[1].clean_text == "Tokyo Station"
    assert translated.units[1].line_type == "sign"


def test_translate_dialogue_preserves_metadata() -> None:
    unit = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text="Good morning",
        clean_text="Good morning",
        prefix="",
        suffix="",
        start_ms=500,
        end_ms=1500,
        style="MainStyle",
        actor="Alice",
        layer=2,
    )
    collection = ClassifiedUnitCollection(units=[unit])
    fake_llm = FakeLLM(responses={"Good morning": "Bom dia"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated = stage.translate_collection(collection)
    res = translated.units[0]
    assert res.clean_text == "Bom dia"
    assert res.actor == "Alice"
    assert res.layer == 2
    assert res.style == "MainStyle"
    assert res.start_ms == 500
    assert res.end_ms == 1500


def test_translate_dialogue_stage_metadata() -> None:
    assert StageTranslateDialogue.name == "translate_dialogue"
    assert StageTranslateDialogue.translates is True
    assert StageTranslateDialogue.scope is StageScope.EPISODE
    assert StageTranslateDialogue.inputs == ("normalize", "classify")
    assert StageTranslateDialogue.enabled_by_default is True
    assert "translate_dialogue" in REGISTRY


def test_translate_dialogue_fallback_when_markers_lost() -> None:
    from types import SimpleNamespace

    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit
    from translaterany.subtitles.texts import UnitTexts

    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[
            Unit(id="u1", style="Default", text="Hello ⟦1⟧world⟦2⟧!", markers=2, events=[0]),
            Unit(id="u2", style="Default", text="Normal text", markers=0, events=[1]),
        ],
    )
    classification = Classification(
        main_style="Default",
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule="test"),
            "u2": UnitClass(type="dialogue", uncertain=False, rule="test"),
        },
        counts={"dialogue": 2},
        scenes=[],
    )

    class MockInputs:
        def json(self, name: str, model: type):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            raise ValueError(name)

    captured_output: UnitTexts | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured_output
            captured_output = obj

    # FakeLLM devolve u1 sem os marcadores ⟦1⟧ e ⟦2⟧ (perdidos) e u2 traduzido normalmente
    fake_llm = FakeLLM(responses={"Hello ⟦1⟧world⟦2⟧!": "Olá mundo!", "Normal text": "Texto normal"})
    stage = StageTranslateDialogue(client=fake_llm)

    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
    )
    stage.run(ctx)  # type: ignore[arg-type]

    assert captured_output is not None
    # u1 perdeu marcadores -> fallback para o texto original
    assert captured_output.texts["u1"] == "Hello ⟦1⟧world⟦2⟧!"
    # u2 não tinha marcadores -> traduzido com sucesso
    assert captured_output.texts["u2"] == "Texto normal"


def test_translate_dialogue_bubbles_up_transient_error(monkeypatch) -> None:
    from types import SimpleNamespace

    import pytest

    from translaterany.llm.client import LLMClient, LLMTransientError
    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit

    class FailingLLM(LLMClient):
        def generate(self, request):
            raise LLMTransientError("API connection timeout")

    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="u1", style="Default", text="Hello world", markers=0, events=[0])],
    )
    classification = Classification(
        main_style="Default",
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="test")},
        counts={"dialogue": 1},
        scenes=[],
    )

    class MockInputs:
        def json(self, name: str, model: type):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            raise ValueError(name)

    stage = StageTranslateDialogue(client=FailingLLM())
    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=SimpleNamespace(json=lambda x: None),
        llm=FailingLLM(),
    )

    with pytest.raises(LLMTransientError, match="API connection timeout"):
        stage.run(ctx)  # type: ignore[arg-type]


def test_translate_dialogue_options_and_doctor_checks() -> None:
    from translaterany.config.loader import ResolvedConfig
    from translaterany.config.model import LLMConfig, ModelConfig, ProfileConfig
    from translaterany.stages.translate_dialogue import TranslateDialogueOptions

    opts = TranslateDialogueOptions(
        model="custom-translate",
        fallback_model="custom-fallback",
        max_tokens_per_batch=400,
        max_context_lines=3,
    )
    stage = StageTranslateDialogue(opts)
    assert stage.options.model == "custom-translate"
    assert stage.options.fallback_model == "custom-fallback"
    assert stage.options.max_tokens_per_batch == 400
    assert stage.options.max_context_lines == 3

    # doctor_checks com perfil local (usa ollama)
    cfg_local = ResolvedConfig(
        source=None,
        data_dir=Path("/tmp"),
        log_level="INFO",
        stages=(stage,),
        llm=LLMConfig(profile="local"),
    )
    checks_local = stage.doctor_checks(cfg_local)
    assert len(checks_local) == 2
    check_names = [c.name for c in checks_local]
    assert "ollama" in check_names
    assert "ollama_models" in check_names

    # doctor_checks com perfil nuvem sem ollama
    cfg_nuvem = ResolvedConfig(
        source=None,
        data_dir=Path("/tmp"),
        log_level="INFO",
        stages=(stage,),
        llm=LLMConfig(
            profile="nuvem",
            profiles={"nuvem": ProfileConfig(translate="gpt-4o", review="gpt-4o")},
            models={"gpt-4o": ModelConfig(provider="openai", model="gpt-4o")},
        ),
    )
    checks_nuvem = stage.doctor_checks(cfg_nuvem)
    assert len(checks_nuvem) == 0


@needs_mkvtoolnix
def test_pipeline_integration_translate_dialogue(data_dir: Path, synthetic_series: Path) -> None:
    from pipeline_helpers import artifact

    from translaterany.library import discover
    from translaterany.pipeline.artifacts import ArtifactStore
    from translaterany.pipeline.runner import Runner
    from translaterany.stages.classify import ClassifyStage
    from translaterany.stages.extract import ExtractStage
    from translaterany.stages.normalize import NormalizeStage
    from translaterany.stages.select_track import SelectTrackStage
    from translaterany.stages.write import WriteStage

    fake_llm = FakeLLM(
        responses={
            "Where are we going, friend?": "Aonde vamos, amigo?",
            "To the ⟦1⟧old⟦2⟧ station.": "Para a ⟦1⟧velha⟦2⟧ estação.",
        }
    )
    stages = [
        SelectTrackStage(),
        ExtractStage(),
        NormalizeStage(),
        ClassifyStage(),
        StageTranslateDialogue(),
        WriteStage(),
    ]
    store = ArtifactStore(data_dir)
    series, episodes = discover(synthetic_series)
    summary = Runner(stages, store, fake_llm).run(series, episodes)
    assert not summary.failed

    written_ass = artifact(store, series, episodes[0], "write.ass").read_text(encoding="utf-8")
    assert "; TranslaterAny" in written_ass
    assert "Aonde vamos, amigo?" in written_ass
    assert r"{\i1}velha{\i0}" in written_ass
    assert "Estação Central" in written_ass  # Placa não traduzida por diálogo
