"""Etapa review_meaning (M6)."""

from types import SimpleNamespace

from translaterany.config.model import AppConfig
from translaterany.llm.client import LLMOutputError
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages.review_meaning import ReviewMeaningStage
from translaterany.subtitles.classify import Classification, Scene, UnitClass
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit
from translaterany.subtitles.scene_analysis import LineContext, SceneAnalysisDoc
from translaterany.subtitles.texts import UnitTexts


def ev(i: int, unit: str) -> EventInfo:
    return EventInfo(
        index=i, line_no=i, kind="dialogue", style="Default", start_ms=i * 3000, end_ms=i * 3000 + 2500,
        layer=0, name="", prefix="", text="t", markers=[], suffix="", drawing=False, unit=unit,
    )  # fmt: skip


DOC = NormalizedDoc(
    encoding=Encoding(bom=False, newline="\n"), format=[],
    events=[ev(0, "u1"), ev(1, "u2"), ev(2, "u3"), ev(3, "u4")],
    units=[Unit(id="u1", style="Default", text="What's this I hear?", markers=0, events=[0]),
           Unit(id="u2", style="Default", text="You cheated on all your tests.", markers=0, events=[1]),
           Unit(id="u3", style="Default", text="Wait for me...", markers=0, events=[2]),
           Unit(id="u4", style="Default", text="...I'm coming!", markers=0, events=[3])],
)  # fmt: skip
CLASSES = Classification(main_style="Default", counts={},
                         units={u: UnitClass(type="dialogue", uncertain=False, rule="r")
                                for u in ("u1", "u2", "u3", "u4")},
                         scenes=[Scene(id="s1", start_ms=0, end_ms=6000, events=[0, 1]),
                                 Scene(id="s2", start_ms=6000, end_ms=12000, events=[2, 3])])  # fmt: skip
MERGED = MergedUnitsDoc(units=[
    CompositeUnit(composite_id="u1", unit_ids=["u1"], durations_ms=[2500], clean_text="",
                  text_with_markers="What's this I hear?"),
    CompositeUnit(composite_id="u2", unit_ids=["u2"], durations_ms=[2500], clean_text="",
                  text_with_markers="You cheated on all your tests."),
    CompositeUnit(composite_id="u3+u4", unit_ids=["u3", "u4"], durations_ms=[2500, 2500], clean_text="",
                  text_with_markers="Wait for me... ...I'm coming!"),
], merged_count=1)  # fmt: skip
SCENE = SceneAnalysisDoc(lines={"u1": LineContext(speaker="Yumi", tone="teasing")})
DIALOGUE = UnitTexts(texts={"u1": "Que barulho é esse?", "u2": "Você colou em tudo, seu merda.",
                            "u3+u4": "Espera... já vou!"}, used_terms={"Yu": "abc"})  # fmt: skip


class Inputs:
    def __init__(self, dialogue: UnitTexts = DIALOGUE) -> None:
        self.data = {"normalize": DOC, "classify": CLASSES, "merge_sentences": MERGED, "scene_analysis": SCENE,
                     "translate_dialogue": dialogue}  # fmt: skip

    def json(self, name, model):
        return self.data[name]


class Output:
    doc: UnitTexts | None = None

    def json(self, model) -> None:
        Output.doc = model


def run(llm, dialogue: UnitTexts = DIALOGUE):
    stage = ReviewMeaningStage()
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(dialogue), output=Output(), llm=llm, metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    return Output.doc, metrics.counters, stage


def test_applies_valid_edits_per_scene_block() -> None:
    prompts = []

    def script(req):
        prompts.append(req.prompt)
        if '"u2"' in req.prompt:
            return EditsResponse(edits=[LineEdit(id="u1", new="Que história é essa?"),
                                        LineEdit(id="u2", new="Você colou em todas as provas.")])  # fmt: skip
        return EditsResponse()

    doc, counters, _ = run(FakeLLM(script))
    assert len(prompts) == 2  # uma chamada por cena
    assert doc.texts == {
        "u1": "Que história é essa?",
        "u2": "Você colou em todas as provas.",
        "u3+u4": "Espera... já vou!",
    }
    assert doc.used_terms == {"Yu": "abc"}
    assert counters["lines_read"] == 3 and counters["lines_targeted"] == 3
    assert counters["blocks"] == 2 and counters["edits_proposed"] == 2 and counters["edits_applied"] == 2
    assert '"sinais": ["profanity_added"]' in prompts[0] and "Yumi" in prompts[0]


def test_invalid_edit_rejected_and_failed_block_passes_through() -> None:
    def script(req):
        if '"u2"' in req.prompt:
            return EditsResponse(edits=[LineEdit(id="u1", new="Que porra é essa?")])  # piora: palavrão novo em u1
        raise LLMOutputError("json inválido")

    doc, counters, _ = run(FakeLLM(script))
    assert doc.texts == DIALOGUE.texts
    assert counters["rejected_worse"] == 1 and counters["blocks_failed"] == 1 and counters["edits_applied"] == 0


def test_nothing_to_review_writes_input_without_calls() -> None:
    llm = FakeLLM()  # qualquer chamada lançaria LLMConfigError
    doc, counters, _ = run(llm, UnitTexts())
    assert doc.texts == {} and llm.calls == [] and counters.get("blocks", 0) == 0


def test_bind_pipeline_picks_last_dialogue_stage_and_limits() -> None:
    from translaterany.pipeline.registry import REGISTRY

    previous = [REGISTRY.get(n)() for n in ("normalize", "classify", "translate_dialogue")]
    stage = ReviewMeaningStage()
    stage.bind_pipeline(previous, AppConfig.model_validate({"checks": {"max_cps": 15}}))
    assert stage.dialogue_input == "translate_dialogue" and stage.max_cps == 15.0
    assert "merge_sentences" not in stage.inputs and "translate_dialogue" in stage.inputs
