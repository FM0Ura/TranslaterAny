from translaterany.llm.fake import FakeLLM
from translaterany.memory.models import CharacterEntry, CharacterRole, Gender
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.scene_analysis import LineContext
from translaterany.subtitles.translator import DialogueBatchTranslator


def test_translator_injects_honorifics_and_profanity_policies():
    fake_llm = FakeLLM(responses=['{"translations": [{"id": "u1", "text": "Tadokoro-senpai, que droga!"}]}'])
    translator = DialogueBatchTranslator(
        client=fake_llm,
        model_name="translate",
        honorifics_policy="keep",
        profanity_policy="faithful",
    )
    lines = [DialogueLine(id="u1", text="Tadokoro-senpai, damn it!")]
    res = translator.translate_lines(lines)
    assert res["u1"] == "Tadokoro-senpai, que droga!"

    # Verifica que as políticas foram instruídas no system prompt ou prompt
    assert "honorific" in fake_llm.last_prompt.lower()
    assert "profanity" in fake_llm.last_prompt.lower()


def test_translator_instructs_neutral_gender_on_low_confidence():
    fake_llm = FakeLLM(responses=['{"translations": [{"id": "u1", "text": "Tenho certeza disso."}]}'])
    line_ctx = {"u1": LineContext(speaker="Unknown", confidence="low")}
    translator = DialogueBatchTranslator(
        client=fake_llm,
        model_name="translate",
        line_contexts=line_ctx,
    )
    lines = [DialogueLine(id="u1", text="I am certain of this.")]
    res = translator.translate_lines(lines)
    assert res["u1"] == "Tenho certeza disso."
    assert "neutral" in fake_llm.last_prompt.lower()


def test_stage_translate_dialogue_consumes_merged_units_and_skips_tm():
    from types import SimpleNamespace
    from translaterany.stages.translate_dialogue import StageTranslateDialogue
    from translaterany.stages.translation_memory import TranslationMemoryArtifact
    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit

    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[
            Unit(id="u1", style="Default", text="TM line", markers=0, events=[0]),
            Unit(id="u2", style="Default", text="Look ahead,", markers=0, events=[1]),
            Unit(id="u3", style="Default", text="it is dangerous.", markers=0, events=[2]),
        ],
    )
    classification = Classification(
        main_style="Default",
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule=""),
            "u2": UnitClass(type="dialogue", uncertain=False, rule=""),
            "u3": UnitClass(type="dialogue", uncertain=False, rule=""),
        },
        counts={},
        scenes=[],
    )
    tm_art = TranslationMemoryArtifact(matched_units={"u1": "Linha da TM"})
    merged_doc = MergedUnitsDoc(
        units=[
            CompositeUnit(
                composite_id="u1",
                unit_ids=["u1"],
                durations_ms=[1000],
                clean_text="TM line",
                text_with_markers="TM line",
            ),
            CompositeUnit(
                composite_id="u2+u3",
                unit_ids=["u2", "u3"],
                durations_ms=[1000, 1500],
                clean_text="Look ahead, it is dangerous.",
                text_with_markers="Look ahead, it is dangerous.",
            ),
        ]
    )

    class MockInputs:
        def json(self, name: str, model: type):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name == "translation_memory":
                return tm_art
            if name == "merge_sentences":
                return merged_doc
            raise ValueError(name)

    captured_output = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured_output
            captured_output = obj

    fake_llm = FakeLLM(responses={"Look ahead, it is dangerous.": "Olhe para frente, é perigoso."})
    stage = StageTranslateDialogue(client=fake_llm)
    ctx = SimpleNamespace(inputs=MockInputs(), output=MockOutput(), llm=fake_llm)
    stage.run(ctx)  # type: ignore[arg-type]

    assert captured_output is not None
    assert captured_output.texts["u1"] == "Linha da TM"
    assert captured_output.texts["u2+u3"] == "Olhe para frente, é perigoso."
    assert len(fake_llm.calls) == 1

