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


def test_gate_reset_clears_seen_hashes_on_run() -> None:
    from translaterany.stages.qa_loop import QALoopStage
    from translaterany.stages.treatment_consistency import TreatmentConsistencyStage

    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[],
    )
    classification = Classification(
        main_style="Default",
        units={},
        counts={},
        scenes=[],
    )

    class MockInputs:
        def json(self, name: str, model: type = object):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name in ("translate_dialogue", "colloquial", "redistribute_sentences"):
                return UnitTexts(texts={})
            raise ValueError(name)

    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=SimpleNamespace(json=lambda obj: None),
        llm=FakeLLM([]),
        series=SimpleNamespace(key="test"),
        config=None,
    )

    # 1. StageTranslateDialogue
    td = StageTranslateDialogue(client=ctx.llm)
    td.gate.seen_hashes["u1"] = {"hash123"}
    td.run(ctx)
    assert len(td.gate.seen_hashes) == 0

    # 2. DialogueRefineStage subclass (TreatmentConsistencyStage)
    tc = TreatmentConsistencyStage()
    tc.gate.seen_hashes["u1"] = {"hash123"}
    tc.run(ctx)
    assert len(tc.gate.seen_hashes) == 0

    # 3. QALoopStage
    qa = QALoopStage()
    qa.gate.seen_hashes["u1"] = {"hash123"}
    qa.run(ctx)
    assert len(qa.gate.seen_hashes) == 0


def test_write_stage_bind_pipeline_respects_explicit_user_choice() -> None:
    from translaterany.stages.write import WriteOptions, WriteStage

    # Usuário escolheu explicitamente "redistribute_sentences"
    stage = WriteStage(WriteOptions(text_source="redistribute_sentences"))
    assert stage.options.text_source == "redistribute_sentences"

    # Ao conectar no pipeline onde a última etapa com texto é qa_loop
    stage.bind_pipeline(
        [
            SimpleNamespace(name="redistribute_sentences", produces_texts=True),
            SimpleNamespace(name="qa_loop", produces_texts=True),
        ],
        None,
    )
    assert stage.options.text_source == "redistribute_sentences"

    # Com opções padrão (sem definição explícita), vincula ao último
    default_stage = WriteStage(WriteOptions())
    default_stage.bind_pipeline(
        [
            SimpleNamespace(name="redistribute_sentences", produces_texts=True),
            SimpleNamespace(name="qa_loop", produces_texts=True),
        ],
        None,
    )
    assert default_stage.options.text_source == "qa_loop"


def test_translate_dialogue_composite_avoids_cpl_gate() -> None:
    from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc

    long_text = "Esta é uma fala bastante longa traduzida que passa de quarenta e dois caracteres."
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="u1", style="Default", text="Original text continuing", markers=0, events=[0])],
    )
    classification = Classification(
        main_style="Default",
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="test")},
        counts={"dialogue": 1},
        scenes=[],
    )
    comp = CompositeUnit(
        composite_id="u1+u2",
        unit_ids=["u1", "u2"],
        text_with_markers="Original text continuing",
        clean_text="Original text continuing",
        durations_ms=[3000, 3000],
    )
    merged_doc = MergedUnitsDoc(units=[comp])

    class MockInputs:
        def json(self, name: str, model: type = object):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name == "merge_sentences":
                return merged_doc
            raise ValueError(name)

    resp = TranslationBatch(items=[TranslationItem(id="u1+u2", text=long_text)])
    fake_llm = FakeLLM([resp])
    stage = StageTranslateDialogue(client=fake_llm)

    captured: UnitTexts | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
        metrics=SimpleNamespace(count=lambda *a, **k: None),
    )
    stage.run(ctx)
    assert captured is not None
    # Deve aceitar a fala na primeira chamada sem retentativas por CPL (pois é composta)
    assert len(fake_llm.calls) == 1
    assert captured.texts["u1+u2"] == long_text

