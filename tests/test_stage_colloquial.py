"""Etapa colloquial (M6)."""

import json
from types import SimpleNamespace

import test_stage_review_meaning as base  # reaproveita DOC, CLASSES, MERGED, SCENE

from translaterany.llm.fake import FakeLLM
from translaterany.memory.models import CharacterEntry
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages import refine_base
from translaterany.stages.colloquial import ColloquialStage
from translaterany.subtitles.scene_analysis import LineContext, SceneAnalysisDoc
from translaterany.subtitles.texts import UnitTexts

PRE = UnitTexts(texts={"u1": "No entanto, para onde o gato foi?", "u2": "Você mentiu sobre tudo, seu merda.",
                       "u3+u4": "Espera... já vou!"})  # fmt: skip
REVIEWED = UnitTexts(texts={"u1": "No entanto, para onde o gato foi?", "u2": "Você mentiu sobre todas as receitas.",
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
        return EditsResponse(edits=[LineEdit(id="u1", new="Mas para onde o gato foi?"),
                                    LineEdit(id="u3+u4", new="Peraí... tô indo!")])  # u3+u4 não é alvo  # fmt: skip

    doc, counters = run(FakeLLM(script))
    assert len(prompts) == 1  # a cena 2 não tem alvo: nenhuma chamada
    assert '"editavel": false' in prompts[0]  # u2 vai como contexto
    assert doc.texts["u1"] == "Mas para onde o gato foi?" and doc.texts["u3+u4"] == "Espera... já vou!"
    assert counters["lines_targeted"] == 1 and counters["rejected_unknown_id"] == 1


def test_reversal_to_pre_review_text_is_blocked_and_counted() -> None:
    def script(req):
        return EditsResponse(edits=[LineEdit(id="u2", new="Você mentiu sobre tudo, seu merda.")])

    stage = ColloquialStage()
    stage.select_targets = lambda ids, data: {i: ["speech_style"] for i in ids}  # todos alvo
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(), output=base.Output(), llm=FakeLLM(script), metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    assert base.Output.doc.texts["u2"] == "Você mentiu sobre todas as receitas."
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


def test_style_alone_does_not_target_but_reinforces_and_reaches_the_prompt(monkeypatch) -> None:
    yumi = CharacterEntry(name="Yumi", speech_style="fala solta e brincalhona")
    monkeypatch.setattr(refine_base, "load_all_characters", lambda store, key: [yumi])
    inputs = Inputs()
    # a Yumi também fala u2 (sem sinal de texto duro): estilo sozinho não pode escolhê-la
    teasing = LineContext(speaker="Yumi", tone="teasing")
    inputs.data["scene_analysis"] = SceneAnalysisDoc(lines={"u1": teasing, "u2": teasing})
    prompts = []

    def script(req):
        prompts.append(json.loads(req.prompt))
        return EditsResponse()

    stage = ColloquialStage()
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=inputs, output=base.Output(), llm=FakeLLM(script), metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    assert metrics.counters["lines_targeted"] == 1
    by_id = {item["id"]: item for item in prompts[0]}
    assert "formal_connective" in by_id["u1"]["sinais"] and by_id["u1"]["sinais"][-1] == "speech_style"
    assert by_id["u1"]["estilo"] == "fala solta e brincalhona" and by_id["u1"]["editavel"] is True
    assert "estilo" not in by_id["u2"] and by_id["u2"]["editavel"] is False  # contexto não leva o estilo


def test_stage_version_was_bumped_to_invalidate_cache() -> None:
    assert ColloquialStage.version == "3"
