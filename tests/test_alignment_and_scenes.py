"""Uso real (Charlotte S01E01): uma fala por chamada evita desalinhamento; análise de cena por cena."""

from translaterany.llm.fake import FakeLLM
from translaterany.memory.models import CharacterEntry
from translaterany.stages.scene_analysis import SceneAnalysisOptions
from translaterany.stages.translate_dialogue import TranslateDialogueOptions
from translaterany.stages.translate_signs import TranslateSignsOptions
from translaterany.stages.translate_songs import TranslateSongsOptions
from translaterany.subtitles.chunking import DialogueLine, create_dialogue_batches
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import LineContext, SceneAnalysisDoc, analyze_scenes
from translaterany.subtitles.translator import DialogueBatchTranslator, TranslationBatch, TranslationItem


def lines(n: int) -> list[DialogueLine]:
    return [DialogueLine(id=f"u{i}", text=f"Line number {i}.") for i in range(1, n + 1)]


def test_max_lines_per_batch_limits_batch_size() -> None:
    assert [len(b.lines) for b in create_dialogue_batches(lines(3), max_lines_per_batch=1)] == [1, 1, 1]
    assert [len(b.lines) for b in create_dialogue_batches(lines(5), max_lines_per_batch=2)] == [2, 2, 1]
    assert [len(b.lines) for b in create_dialogue_batches(lines(5), max_lines_per_batch=None)] == [5]


def test_translation_options_default_to_one_line_per_call() -> None:
    assert TranslateDialogueOptions().max_lines_per_batch == 1
    assert TranslateSignsOptions().max_lines_per_batch == 1
    assert TranslateSongsOptions().max_lines_per_batch == 1


def test_translator_sends_one_line_per_call_with_previous_translation_as_context() -> None:
    prompts: list[str] = []

    def script(req):
        prompts.append(req.prompt)
        line_id = next(line.split("]")[0][1:] for line in req.prompt.splitlines() if line.startswith("[u"))
        return TranslationBatch(items=[TranslationItem(id=line_id, text=f"PT {line_id}")])

    tr = DialogueBatchTranslator(FakeLLM(script), max_context_lines=2, max_lines_per_batch=1)
    assert tr.translate_lines(lines(3)) == {"u1": "PT u1", "u2": "PT u2", "u3": "PT u3"}
    assert len(prompts) == 3
    assert "[u2]" not in prompts[0] and "PT u1" in prompts[1]


def test_translator_accepts_bracketed_ids() -> None:
    llm = FakeLLM(lambda req: TranslationBatch(items=[TranslationItem(id="[u1]", text="Ah, isso eu não conto.")]))
    tr = DialogueBatchTranslator(llm, max_lines_per_batch=1)
    assert tr.translate_lines(lines(1)) == {"u1": "Ah, isso eu não conto."}


def test_translator_accepts_single_item_with_wrong_id_in_single_line_call() -> None:
    llm = FakeLLM(lambda req: TranslationBatch(items=[TranslationItem(id="1", text="Linha um.")]))
    tr = DialogueBatchTranslator(llm, max_lines_per_batch=1)
    assert tr.translate_lines(lines(1)) == {"u1": "Linha um."}


def _merged() -> MergedUnitsDoc:
    def comp(cid: str) -> CompositeUnit:
        ids = cid.split("+")
        return CompositeUnit(composite_id=cid, unit_ids=ids, durations_ms=[1000] * len(ids), clean_text=f"text {cid}",
                             text_with_markers=f"text {cid}")  # fmt: skip

    return MergedUnitsDoc(units=[comp("u1"), comp("u2+u3"), comp("u4"), comp("u5")])


UNIT_EVENTS = {"u1": [0], "u2": [1], "u3": [2], "u4": [3], "u5": [9]}  # u5: evento fora de qualquer cena
SCENES = [Scene(id="s1", start_ms=0, end_ms=3000, events=[0, 1, 2]), Scene(id="s2", start_ms=5000, end_ms=6000,
                                                                            events=[3])]  # fmt: skip


def test_analyze_scenes_calls_model_once_per_scene_with_only_its_lines() -> None:
    prompts: list[str] = []

    def script(req):
        prompts.append(req.prompt)
        ids = [cid for cid in ("u1", "u2+u3", "u4", "u5") if f'"{cid}"' in req.prompt]
        return SceneAnalysisDoc(lines={cid: LineContext(speaker="Yu", confidence="high") for cid in ids})

    doc = analyze_scenes(_merged(), SCENES, [CharacterEntry(name="Yu")], "syn", FakeLLM(script),
                         unit_events=UNIT_EVENTS)  # fmt: skip
    assert len(prompts) == 3  # s1, s2 e as falas sem cena
    assert '"u1"' in prompts[0] and '"u2+u3"' in prompts[0] and '"u4"' not in prompts[0]
    assert '"u4"' in prompts[1] and '"u5"' in prompts[2]
    assert all(doc.lines[cid].speaker == "Yu" for cid in ("u1", "u2+u3", "u4", "u5"))


def test_analyze_scenes_splits_long_scenes_and_isolates_failures() -> None:
    calls: list[str] = []

    def script(req):
        calls.append(req.prompt)
        if '"u4"' in req.prompt:
            raise RuntimeError("falhou só esta cena")
        ids = [cid for cid in ("u1", "u2+u3") if f'"{cid}"' in req.prompt]
        return SceneAnalysisDoc(lines={cid: LineContext(speaker="Yu", confidence="high") for cid in ids})

    doc = analyze_scenes(_merged(), SCENES, [], "", FakeLLM(script), unit_events=UNIT_EVENTS, max_lines_per_call=1)
    assert len(calls) == 4  # s1 dividida em 2 + s2 + sem cena
    assert doc.lines["u1"].speaker == "Yu" and doc.lines["u2+u3"].speaker == "Yu"
    assert doc.lines["u4"].confidence == "low"  # só a cena que falhou caiu no fallback


def test_scene_analysis_option_default() -> None:
    assert SceneAnalysisOptions().max_lines_per_call == 40
