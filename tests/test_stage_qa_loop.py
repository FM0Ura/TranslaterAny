"""Testes da etapa QALoopStage e relatório qa_report.json."""

from pathlib import Path
from types import SimpleNamespace

from translaterany.config.model import QALoopOptions
from translaterany.llm.client import FakeLLM
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.stages.qa_loop import QALoopStage, QAReport
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import TranslationBatch, TranslationItem


def test_qa_report_serialization() -> None:
    report = QAReport(
        rounds_executed=1,
        extra_calls_used=2,
        blame_summary={"colloquial": 1},
        interventions=[{"unit_id": "u1", "blamed_stage": "colloquial", "outcome": "fixed"}],
        edit_rate=0.05,
    )
    data = report.to_dict()
    assert data["rounds_executed"] == 1
    assert data["blame_summary"]["colloquial"] == 1
    assert data["extra_calls_used"] == 2
    assert data["edit_rate"] == 0.05
    assert len(data["interventions"]) == 1
    assert data["interventions"][0]["outcome"] == "fixed"


class MockInputs:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def json(self, name: str, model: type = object):
        if name in self._data:
            return self._data[name]
        raise KeyError(name)


class MockOutput:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.doc: UnitTexts | None = None

    def json(self, model: object) -> None:
        if isinstance(model, UnitTexts):
            self.doc = model


def _build_context(
    tmp_path: Path,
    inputs_data: dict[str, object],
    llm: FakeLLM,
) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=MockInputs(inputs_data),
        output=MockOutput(tmp_path),
        llm=llm,
        metrics=StageMetrics(),
        store=None,
        series=SimpleNamespace(key="test-series"),
        episode=SimpleNamespace(key="S01E01"),
    )


def test_qa_loop_clean_execution(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Hello world.",
                markers=[],
                suffix="",
                drawing=False,
                unit="u1",
            )
        ],
        units=[Unit(id="u1", style="Default", text="Hello world.", markers=0, events=[0])],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r")},
        scenes=[],
    )
    history_dialogue = UnitTexts(texts={"u1": "Olá mundo."})
    history_redistribute = UnitTexts(texts={"u1": "Olá mundo."})

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": history_dialogue,
        "redistribute_sentences": history_redistribute,
    }
    llm = FakeLLM([])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage()
    stage.run(ctx)

    assert ctx.output.doc is not None
    assert ctx.output.doc.texts["u1"] == "Olá mundo."
    report_file = tmp_path / "qa_report.json"
    assert report_file.exists()
    assert '"rounds_executed": 1' in report_file.read_text(encoding="utf-8")
    assert '"interventions": []' in report_file.read_text(encoding="utf-8")


def test_qa_loop_fixes_defect_via_blame_and_llm(tmp_path: Path) -> None:
    # Cenário: translate_dialogue limpo, colloquial introduziu prompt_leak
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Bom dia a todos.",
                markers=[],
                suffix="",
                drawing=False,
                unit="u1",
            )
        ],
        units=[Unit(id="u1", style="Default", text="Good morning everyone.", markers=0, events=[0])],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r")},
        scenes=[],
    )

    clean_trans = UnitTexts(texts={"u1": "Bom dia a todos."})
    leak_colloquial = UnitTexts(texts={"u1": "máx. 10 Bom dia a todos."})
    redist = UnitTexts(texts={"u1": "máx. 10 Bom dia a todos."})

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": clean_trans,
        "colloquial": leak_colloquial,
        "redistribute_sentences": redist,
    }

    # FakeLLM devolve o texto corrigido
    resp_fixed = TranslationBatch(items=[TranslationItem(id="u1", text="Bom dia a todos.")])
    llm = FakeLLM([resp_fixed])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage()
    stage.run(ctx)

    assert ctx.output.doc is not None
    assert ctx.output.doc.texts["u1"] == "Bom dia a todos."

    report_file = tmp_path / "qa_report.json"
    assert report_file.exists()
    report_data = report_file.read_text(encoding="utf-8")
    assert '"colloquial": 1' in report_data
    assert '"outcome": "fixed"' in report_data


def test_qa_loop_never_worsen_reverts(tmp_path: Path) -> None:
    # Cenário: saída do LLM piora (quebra marcadores) -> revertida
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Texto ⟦1⟧ teste.",
                markers=["⟦1⟧"],
                suffix="",
                drawing=False,
                unit="u1",
            )
        ],
        units=[Unit(id="u1", style="Default", text="Source ⟦1⟧ test.", markers=1, events=[0])],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r")},
        scenes=[],
    )

    clean_trans = UnitTexts(texts={"u1": "Texto ⟦1⟧ teste."})
    leak_colloquial = UnitTexts(texts={"u1": "máx. 10 Texto ⟦1⟧ teste."})
    redist = UnitTexts(texts={"u1": "máx. 10 Texto ⟦1⟧ teste."})

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": clean_trans,
        "colloquial": leak_colloquial,
        "redistribute_sentences": redist,
    }

    # Resposta que quebra marcadores e tem vazamento ainda pior
    resp_worse = TranslationBatch(items=[TranslationItem(id="u1", text="máx. 20 Texto sem marcadores.")])
    resp_worse_round2 = TranslationBatch(items=[TranslationItem(id="u1", text="máx. 30 Pior ainda.")])
    llm = FakeLLM([resp_worse, resp_worse_round2])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage()
    stage.run(ctx)

    assert ctx.output.doc is not None
    # Deve reter a melhor versão prévia
    assert ctx.output.doc.texts["u1"] == "máx. 10 Texto ⟦1⟧ teste."

    report_file = tmp_path / "qa_report.json"
    assert report_file.exists()
    report_data = report_file.read_text(encoding="utf-8")
    assert '"reverted"' in report_data or '"exhausted"' in report_data


def test_qa_loop_budget_exhaustion(tmp_path: Path) -> None:
    # Cenário: teto de chamadas atingido
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Erro 1",
                markers=[],
                suffix="",
                drawing=False,
                unit="u1",
            ),
            EventInfo(
                index=1,
                line_no=1,
                kind="dialogue",
                style="Default",
                start_ms=2000,
                end_ms=4000,
                layer=0,
                name="",
                prefix="",
                text="Erro 2",
                markers=[],
                suffix="",
                drawing=False,
                unit="u2",
            ),
        ],
        units=[
            Unit(id="u1", style="Default", text="Error 1", markers=0, events=[0]),
            Unit(id="u2", style="Default", text="Error 2", markers=0, events=[1]),
        ],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule="r"),
            "u2": UnitClass(type="dialogue", uncertain=False, rule="r"),
        },
        scenes=[],
    )

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": UnitTexts(texts={"u1": "máx. 10 A", "u2": "máx. 10 B"}),
        "redistribute_sentences": UnitTexts(texts={"u1": "máx. 10 A", "u2": "máx. 10 B"}),
    }

    resp1 = TranslationBatch(items=[TranslationItem(id="u1", text="Texto A corrigido")])
    llm = FakeLLM([resp1])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage(options=QALoopOptions(max_rounds=1, max_extra_calls=1))
    stage.run(ctx)

    assert len(llm.calls) == 1
    report_file = tmp_path / "qa_report.json"
    report_data = report_file.read_text(encoding="utf-8")
    assert '"extra_calls_used": 1' in report_data


def test_qa_loop_ass_syntax_fix(tmp_path: Path) -> None:
    # Cenário: sintaxe ASS inválida (chaves não fechadas) corrigida pelo LLM
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Look at that!",
                markers=[],
                suffix="",
                drawing=False,
                unit="u1",
            )
        ],
        units=[Unit(id="u1", style="Default", text="Look at that!", markers=0, events=[0])],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r")},
        scenes=[],
    )

    clean_trans = UnitTexts(texts={"u1": "Olhe aquilo!"})
    bad_adapt = UnitTexts(texts={"u1": r"{\an8Olhe aquilo!"})  # chaves desbalanceadas
    redist = UnitTexts(texts={"u1": r"{\an8Olhe aquilo!"})

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": clean_trans,
        "adapt": bad_adapt,
        "redistribute_sentences": redist,
    }

    resp = TranslationBatch(items=[TranslationItem(id="u1", text=r"{\an8}Olhe aquilo!")])
    llm = FakeLLM([resp])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage()
    stage.run(ctx)

    assert ctx.output.doc is not None
    assert ctx.output.doc.texts["u1"] == r"{\an8}Olhe aquilo!"
    report_file = tmp_path / "qa_report.json"
    report_data = report_file.read_text(encoding="utf-8")
    assert '"adapt": 1' in report_data
    assert '"outcome": "fixed"' in report_data


def test_qa_loop_oscillation_terminates(tmp_path: Path) -> None:
    # Cenário: saída oscila retornando um texto já visto
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Hello.",
                markers=[],
                suffix="",
                drawing=False,
                unit="u1",
            )
        ],
        units=[Unit(id="u1", style="Default", text="Hello.", markers=0, events=[0])],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r")},
        scenes=[],
    )

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": UnitTexts(texts={"u1": "máx. 10 Olá."}),
        "redistribute_sentences": UnitTexts(texts={"u1": "máx. 10 Olá."}),
    }

    # LLM primeiro devolve 'máx. 20 Olá.', depois oscila voltando para 'máx. 20 Olá.'
    resp1 = TranslationBatch(items=[TranslationItem(id="u1", text="máx. 20 Olá.")])
    resp2 = TranslationBatch(items=[TranslationItem(id="u1", text="máx. 20 Olá.")])
    llm = FakeLLM([resp1, resp2])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage(options=QALoopOptions(max_rounds=2, max_extra_calls=5))
    stage.run(ctx)

    report_file = tmp_path / "qa_report.json"
    report_data = report_file.read_text(encoding="utf-8")
    assert '"exhausted"' in report_data or '"reverted"' in report_data


def test_qa_loop_bind_pipeline() -> None:
    stage = QALoopStage()
    dummy_prev = [
        SimpleNamespace(name="translate_dialogue", produces_texts=True, produces_dialogue=True),
        SimpleNamespace(name="colloquial", produces_texts=True, produces_dialogue=True),
        SimpleNamespace(name="redistribute_sentences", produces_texts=True, produces_dialogue=False),
    ]
    stage.bind_pipeline(dummy_prev, None)
    assert stage.dialogue_input == "redistribute_sentences"
    assert "translate_dialogue" in stage.snapshot_stages
    assert "colloquial" in stage.snapshot_stages
    assert "redistribute_sentences" in stage.inputs


def test_qa_loop_orthography_graceful_pass(tmp_path: Path) -> None:
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[
            EventInfo(
                index=0,
                line_no=0,
                kind="dialogue",
                style="Default",
                start_ms=0,
                end_ms=2000,
                layer=0,
                name="",
                prefix="",
                text="Hello world.",
                markers=[],
                suffix="",
                drawing=False,
                unit="u1",
            )
        ],
        units=[Unit(id="u1", style="Default", text="Hello world.", markers=0, events=[0])],
    )
    classes = Classification(
        main_style="Default",
        counts={},
        units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r")},
        scenes=[],
    )

    inputs = {
        "normalize": doc,
        "classify": classes,
        "translate_dialogue": UnitTexts(texts={"u1": "Olá mundo."}),
        "orthography": UnitTexts(texts={"u1": "máx. 10 Olá mundo."}),
        "redistribute_sentences": UnitTexts(texts={"u1": "máx. 10 Olá mundo."}),
    }

    resp = TranslationBatch(items=[TranslationItem(id="u1", text="Olá mundo.")])
    llm = FakeLLM([resp])
    ctx = _build_context(tmp_path, inputs, llm)

    stage = QALoopStage()
    stage.bind_pipeline(
        [
            SimpleNamespace(name="translate_dialogue", produces_texts=True, produces_dialogue=True),
            SimpleNamespace(name="orthography", produces_texts=True, produces_dialogue=True),
            SimpleNamespace(name="redistribute_sentences", produces_texts=True, produces_dialogue=False),
        ],
        None,
    )
    stage.run(ctx)

    assert ctx.output.doc is not None
    assert ctx.output.doc.texts["u1"] == "Olá mundo."
    report_file = tmp_path / "qa_report.json"
    assert '"outcome": "fixed"' in report_file.read_text(encoding="utf-8")


