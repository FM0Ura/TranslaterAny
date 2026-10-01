"""Testes de integracao do StageGate nas etapas com IA."""

from types import SimpleNamespace

from translaterany.config.model import GatesConfig
from translaterany.llm.client import FakeLLM
from translaterany.pipeline.gates import StageGate
from translaterany.refine.edits import LineEdit
from translaterany.stages.refine_base import apply_edits_with_gate
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import TranslationBatch, TranslationItem


def test_apply_edits_with_gate_rejects_severe_degradation() -> None:
    # Edição tenta introduzir um prompt_leak
    original = {"u1": "Olá mundo."}
    edits = [LineEdit(id="u1", text="máx. 10 caracteres Olá mundo.")]
    result = apply_edits_with_gate(original, edits, gate=StageGate())
    # O portão deve barrar a piora e manter a versão limpa original
    assert result["u1"] == "Olá mundo."


def test_apply_edits_with_gate_applies_clean_edit() -> None:
    original = {"u1": "Olá mundo."}
    edits = [LineEdit(id="u1", text="Olá, mundo maravilhoso!")]
    result = apply_edits_with_gate(original, edits, gate=StageGate())
    assert result["u1"] == "Olá, mundo maravilhoso!"


def test_apply_edits_with_gate_rejects_broken_markers() -> None:
    original = {"u1": "Olá ⟦1⟧mundo⟦2⟧."}
    edits = [LineEdit(id="u1", text="Olá mundo.")]
    result = apply_edits_with_gate(original, edits, gate=StageGate())
    assert result["u1"] == "Olá ⟦1⟧mundo⟦2⟧."


def test_apply_edits_with_gate_disabled() -> None:
    original = {"u1": "Olá mundo."}
    edits = [LineEdit(id="u1", text="máx. 10 caracteres Olá mundo.")]
    gate = StageGate(config=GatesConfig(enabled=False))
    result = apply_edits_with_gate(original, edits, gate=gate)
    assert result["u1"] == "máx. 10 caracteres Olá mundo."


def test_translate_dialogue_retries_with_gate_and_recovers() -> None:
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

    captured_output: UnitTexts | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured_output
            captured_output = obj

    # Primeira chamada devolve prompt_leak; retry com feedback devolve resposta limpa
    resp_bad = TranslationBatch(items=[TranslationItem(id="u1", text="máx. 10 Olá mundo")])
    resp_clean = TranslationBatch(items=[TranslationItem(id="u1", text="Olá mundo")])
    fake_llm = FakeLLM([resp_bad, resp_clean])

    stage = StageTranslateDialogue(client=fake_llm)
    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
        metrics=SimpleNamespace(count=lambda *a, **k: None),
    )
    stage.run(ctx)  # type: ignore[arg-type]

    assert captured_output is not None
    assert captured_output.texts["u1"] == "Olá mundo"
    assert len(fake_llm.calls) == 2  # 1 chamada normal + 1 retry com feedback


def test_translate_dialogue_oscillation_stops_retries() -> None:
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

    captured_output: UnitTexts | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured_output
            captured_output = obj

    # Ambos retornos geram o mesmo prompt_leak idêntico -> oscilação
    resp_bad = TranslationBatch(items=[TranslationItem(id="u1", text="máx. 10 Olá mundo")])
    fake_llm = FakeLLM([resp_bad, resp_bad])

    stage = StageTranslateDialogue(client=fake_llm)
    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
        metrics=SimpleNamespace(count=lambda *a, **k: None),
    )
    stage.run(ctx)  # type: ignore[arg-type]

    assert captured_output is not None
    # Interrompe na oscilação (não continua infinitamente)
    assert len(fake_llm.calls) == 2
