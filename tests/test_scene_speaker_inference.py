"""Inferência determinística de falantes e sinalização de gênero indeterminado (dados sintéticos)."""

from types import SimpleNamespace

from translaterany.llm.fake import FakeLLM
from translaterany.media.audio.models import AcousticSegment
from translaterany.media.audio.voice_bank import VoiceBankDoc, VoiceProfile
from translaterany.memory.models import CharacterEntry, CharacterRole, Gender
from translaterany.subtitles.chunking import ContextLine, DialogueLine, format_batch_prompt
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import (
    LineContext,
    SceneAnalysisDoc,
    analyze_scenes,
    analyze_scenes_multimodal,
)

ALICE = CharacterEntry(name="Alice Brown", gender=Gender.FEMALE, role=CharacterRole.MAIN, aliases=["Ali"])
BOB = CharacterEntry(name="Bob Stone", gender=Gender.MALE, role=CharacterRole.MAIN)
CARL = CharacterEntry(name="Carl Gray", gender=Gender.UNKNOWN, role=CharacterRole.SUPPORTING)
CHARS = [ALICE, BOB, CARL]


def _units(*texts: str) -> MergedUnitsDoc:
    return MergedUnitsDoc(
        units=[
            CompositeUnit(
                composite_id=f"u{i}",
                unit_ids=[f"u{i}"],
                durations_ms=[1000],
                clean_text=t,
                text_with_markers=t,
            )
            for i, t in enumerate(texts, 1)
        ]
    )


def _llm(**lines: LineContext) -> FakeLLM:
    return FakeLLM([SceneAnalysisDoc(lines=dict(lines))])


def _run(doc: MergedUnitsDoc, llm: FakeLLM, times: dict[str, tuple[int, int]] | None = None) -> SceneAnalysisDoc:
    return analyze_scenes(
        doc,
        [Scene(id="s", start_ms=0, end_ms=99999, events=list(range(len(doc.units))))],
        CHARS,
        "Synopsis",
        llm,
        unit_events={u.composite_id: [i] for i, u in enumerate(doc.units)},
        unit_times=times,
    )


# --- sinal de gênero e normalização de confiança -------------------------------------------------


def test_unknown_speaker_never_keeps_medium_or_high_confidence() -> None:
    llm = _llm(u1=LineContext(speaker="Unknown", confidence="medium"))
    out = _run(_units("Hello."), llm)
    assert out.lines["u1"].confidence == "low"
    assert out.lines["u1"].gender_unsafe is True


def test_known_speaker_gets_gender_from_character_and_is_safe() -> None:
    llm = _llm(u1=LineContext(speaker="Alice Brown", confidence="high"))
    ctx = _run(_units("Hello."), llm).lines["u1"]
    assert ctx.speaker_gender == "female"
    assert ctx.gender_unsafe is False


def test_known_speaker_with_unknown_gender_is_flagged_unsafe() -> None:
    llm = _llm(u1=LineContext(speaker="Carl Gray", confidence="high"))
    ctx = _run(_units("Hello."), llm).lines["u1"]
    assert ctx.speaker_gender == "unknown"
    assert ctx.gender_unsafe is True


def test_partial_speaker_name_is_canonicalized_when_unambiguous() -> None:
    llm = _llm(u1=LineContext(speaker="Stone", confidence="high"))
    ctx = _run(_units("Hello."), llm).lines["u1"]
    assert ctx.speaker == "Bob Stone"
    assert ctx.speaker_gender == "male"


def test_fallback_without_client_is_flagged_unsafe() -> None:
    out = analyze_scenes(_units("Hello."), [], CHARS, "", None)
    assert out.lines["u1"].gender_unsafe is True
    assert out.lines["u1"].confidence == "low"


def test_old_artifact_without_new_fields_still_loads() -> None:
    doc = SceneAnalysisDoc.model_validate({"lines": {"u1": {"speaker": "Unknown", "confidence": "low"}}})
    assert doc.lines["u1"].speaker_gender == "unknown"
    assert doc.lines["u1"].gender_unsafe is False
    assert doc.lines["u1"].speaker_source == "llm"


# --- propagação por continuação ------------------------------------------------------------------

_T = {"u1": (0, 1000), "u2": (1100, 2000)}


def _continuation(first: str, second: str, times, first_conf="high") -> LineContext:
    llm = _llm(
        u1=LineContext(speaker="Alice Brown", listener="Bob Stone", confidence=first_conf),
        u2=LineContext(speaker="Unknown", confidence="low"),
    )
    return _run(_units(first, second), llm, times).lines["u2"]


def test_continuation_propagates_speaker_with_medium_confidence() -> None:
    ctx = _continuation("I think we should go,", "and then we leave.", _T)
    assert ctx.speaker == "Alice Brown"
    assert ctx.listener == "Bob Stone"
    assert ctx.confidence == "medium"  # nunca 'high' para um palpite
    assert ctx.speaker_source == "continuation"
    assert ctx.gender_unsafe is False


def test_continuation_not_applied_when_gap_is_large() -> None:
    ctx = _continuation("I think we should go,", "and then we leave.", {"u1": (0, 1000), "u2": (4000, 5000)})
    assert ctx.speaker == "Unknown"


def test_continuation_not_applied_when_next_starts_uppercase() -> None:
    assert _continuation("I think we should go,", "And then we leave.", _T).speaker == "Unknown"


def test_continuation_not_applied_when_previous_is_terminal() -> None:
    assert _continuation("I think we should go.", "and then we leave.", _T).speaker == "Unknown"


def test_continuation_not_applied_when_previous_confidence_is_not_high() -> None:
    assert _continuation("I think we should go,", "and then we leave.", _T, first_conf="medium").speaker == "Unknown"


def test_continuation_not_applied_across_scenes() -> None:
    doc = _units("I think we should go,", "and then we leave.")
    llm = FakeLLM(
        [
            SceneAnalysisDoc(lines={"u1": LineContext(speaker="Alice Brown", confidence="high")}),
            SceneAnalysisDoc(lines={"u2": LineContext(speaker="Unknown")}),
        ]
    )
    scenes = [Scene(id="a", start_ms=0, end_ms=1000, events=[0]), Scene(id="b", start_ms=1000, end_ms=2000, events=[1])]
    out = analyze_scenes(
        doc, scenes, CHARS, "", llm, unit_events={"u1": [0], "u2": [1]}, unit_times=_T
    )
    assert out.lines["u2"].speaker == "Unknown"


# --- autoapresentação ----------------------------------------------------------------------------


def test_self_introduction_resolves_speaker() -> None:
    llm = _llm(u1=LineContext(speaker="Unknown", confidence="low"))
    ctx = _run(_units("I'm Alice, nice to meet you."), llm).lines["u1"]
    assert ctx.speaker == "Alice Brown"
    assert ctx.confidence == "medium"
    assert ctx.speaker_source == "self_introduction"


def test_self_introduction_ignores_possessive_and_third_person() -> None:
    llm = _llm(u1=LineContext(speaker="Unknown", confidence="low"), u2=LineContext(speaker="Unknown"))
    out = _run(_units("I'm Alice's friend.", "This is Alice."), llm)
    assert out.lines["u1"].speaker == "Unknown"
    assert out.lines["u2"].speaker == "Unknown"


def test_alternation_is_not_guessed_from_previous_listener() -> None:
    """Medido em dados reais: alternar pelo ouvinte anterior acerta ~50%, então não se chuta."""
    llm = _llm(
        u1=LineContext(speaker="Alice Brown", listener="Bob Stone", confidence="high"),
        u2=LineContext(speaker="Unknown", confidence="low"),
    )
    out = _run(_units("Are you coming?", "Not sure."), llm, _T)
    assert out.lines["u2"].speaker == "Unknown"


# --- prompt da análise ---------------------------------------------------------------------------


def test_second_block_of_same_scene_receives_previous_lines_as_context() -> None:
    doc = _units("First sentence.", "Second sentence.")
    llm = FakeLLM(
        [
            SceneAnalysisDoc(lines={"u1": LineContext(speaker="Alice Brown", confidence="high")}),
            SceneAnalysisDoc(lines={"u2": LineContext(speaker="Bob Stone", confidence="high")}),
        ]
    )
    analyze_scenes(
        doc,
        [Scene(id="s", start_ms=0, end_ms=9999, events=[0, 1])],
        CHARS,
        "",
        llm,
        unit_events={"u1": [0], "u2": [1]},
        max_lines_per_call=1,
    )
    first, second = llm.calls
    assert "Previous lines" not in first.prompt
    assert "Previous lines" in second.prompt
    assert "Alice Brown" in second.prompt.split("Previous lines")[1].split("Lines:")[0]


def test_analysis_instructions_forbid_high_confidence_for_guesses() -> None:
    llm = _llm(u1=LineContext(speaker="Alice Brown", confidence="high"))
    _run(_units("Hello."), llm)
    assert "NEVER 'high'" in llm.calls[0].instructions


# --- fusão multimodal ----------------------------------------------------------------------------


def _multimodal(llm_ctx: LineContext, acoustic: str, embedding: list[float]) -> LineContext:
    doc = _units("Hello there.")
    bank = VoiceBankDoc(
        profiles=[
            VoiceProfile(
                character_name="Alice Brown", canonical_gender="female", centroid=[1.0, 0.0, 0.0],
                sample_count=50, confidence="high",
            )
        ]
    )
    segs = {"u1": AcousticSegment("u1", 0, 1000, embedding, acoustic)}
    out = analyze_scenes_multimodal(
        merged_doc=doc,
        scenes=[Scene(id="s", start_ms=0, end_ms=5000, events=[0])],
        characters=CHARS,
        voice_bank=bank,
        episode_segments=segs,
        client=_llm(u1=llm_ctx),
    )
    return out.lines["u1"]


def test_acoustic_gender_alone_does_not_raise_confidence_of_unknown_speaker() -> None:
    # centróide distante (sim < 0.80): só há o gênero acústico, que é pouco confiável
    ctx = _multimodal(LineContext(speaker="Unknown", confidence="low"), "female", [0.0, 1.0, 0.0])
    assert ctx.speaker == "Unknown"
    assert ctx.confidence == "low"
    assert ctx.gender_unsafe is True


def test_acoustic_gender_alone_does_not_downgrade_high_confidence() -> None:
    ctx = _multimodal(LineContext(speaker="Bob Stone", confidence="high"), "female", [0.0, 1.0, 0.0])
    assert ctx.confidence == "high"
    assert ctx.speaker_gender == "male"


def test_voice_match_resolves_speaker_and_gender() -> None:
    ctx = _multimodal(LineContext(speaker="Unknown", confidence="low"), "unknown", [0.99, 0.01, 0.0])
    assert ctx.speaker == "Alice Brown"
    assert ctx.confidence == "high"
    assert ctx.speaker_source == "voice"
    assert ctx.speaker_gender == "female"
    assert ctx.gender_unsafe is False


# --- prompt de tradução --------------------------------------------------------------------------


def _prompt(lctx: object, characters=()) -> str:
    return format_batch_prompt(
        [DialogueLine(id="u1", text="Thanks.")],
        [ContextLine(text="Before.")],
        characters=characters,
        line_contexts={"u1": lctx},
    )


def test_prompt_shows_speaker_gender() -> None:
    p = _prompt(LineContext(speaker="Alice Brown", speaker_gender="female", confidence="high"))
    assert "falante: Alice Brown (feminino)" in p
    assert "neutr" not in p


def test_prompt_uses_neutral_phrasing_for_unknown_speaker_even_with_medium_confidence() -> None:
    p = _prompt(SimpleNamespace(speaker="Unknown", listener="Unknown", tone="neutral", confidence="medium"))
    assert "formulação neutra" in p


def test_prompt_uses_neutral_phrasing_when_speaker_gender_is_unknown() -> None:
    p = _prompt(LineContext(speaker="Carl Gray", speaker_gender="unknown", confidence="high"))
    assert "formulação neutra" in p


def test_prompt_falls_back_to_character_list_for_artifacts_without_gender_field() -> None:
    legacy = SimpleNamespace(speaker="Alice Brown", listener="Unknown", tone="neutral", confidence="high")
    p = _prompt(legacy, characters=[ALICE])
    assert "falante: Alice Brown (feminino)" in p
