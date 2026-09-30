"""Etapa colloquial (M6)."""

from types import SimpleNamespace

import test_stage_review_meaning as base  # reaproveita DOC, CLASSES, MERGED, SCENE

from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages.colloquial import ColloquialStage
from translaterany.subtitles.texts import UnitTexts

PRE = UnitTexts(texts={"u1": "No entanto, que história é essa?", "u2": "Você colou em tudo, seu merda.",
                       "u3+u4": "Espera... já vou!"})  # fmt: skip
REVIEWED = UnitTexts(texts={"u1": "No entanto, que história é essa?", "u2": "Você colou em todas as provas.",
                            "u3+u4": "Espera... já vou!"})  # fmt: skip


class Inputs(base.Inputs):
    def __init__(self) -> None:
        super().__init__()
        self.data["translate_dialogue"] = PRE
        self.data["review_meaning"] = REVIEWED


def run(llm):
    stage = ColloquialStage()
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(), output=base.Output(), llm=llm, metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    return base.Output.doc, metrics.counters


def test_only_triaged_lines_are_editable_and_context_edits_are_rejected() -> None:
    prompts = []

    def script(req):
        prompts.append(req.prompt)
        return EditsResponse(edits=[LineEdit(id="u1", new="Mas que história é essa?"),
                                    LineEdit(id="u3+u4", new="Peraí... tô indo!")])  # u3+u4 não é alvo  # fmt: skip

    doc, counters = run(FakeLLM(script))
    assert len(prompts) == 1  # a cena 2 não tem alvo: nenhuma chamada
    assert '"editavel": false' in prompts[0]  # u2 vai como contexto
    assert doc.texts["u1"] == "Mas que história é essa?" and doc.texts["u3+u4"] == "Espera... já vou!"
    assert counters["lines_targeted"] == 1 and counters["rejected_unknown_id"] == 1


def test_reversal_to_pre_review_text_is_blocked_and_counted() -> None:
    def script(req):
        return EditsResponse(edits=[LineEdit(id="u2", new="Você colou em tudo, seu merda.")])

    stage = ColloquialStage()
    stage.select_targets = lambda ids, data: {i: ["speech_style"] for i in ids}  # todos alvo
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(), output=base.Output(), llm=FakeLLM(script), metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    assert base.Output.doc.texts["u2"] == "Você colou em todas as provas."
    assert metrics.counters["reversals"] >= 1


def test_bind_pipeline_finds_pre_review_stage() -> None:
    names = ("normalize", "classify", "translate_dialogue", "review_meaning")
    stage = ColloquialStage()
    stage.bind_pipeline([REGISTRY.get(n)() for n in names], None)
    assert stage.dialogue_input == "review_meaning" and stage.pre_review_input == "translate_dialogue"
    assert "translate_dialogue" in stage.inputs
    alone = ColloquialStage()
    alone.bind_pipeline([REGISTRY.get(n)() for n in ("normalize", "classify", "translate_dialogue")], None)
    assert alone.dialogue_input == "translate_dialogue" and alone.pre_review_input is None
