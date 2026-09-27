from translaterany.llm.fake import FakeLLM
from translaterany.memory.models import CharacterEntry, CharacterRole, Gender
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import LineContext, SceneAnalysisDoc, analyze_scenes


def test_analyze_scenes_with_fake_llm():
    units = [
        CompositeUnit(
            composite_id="u1",
            unit_ids=["u1"],
            durations_ms=[2000],
            clean_text="Who are you?",
            text_with_markers="Who are you?",
            speaker="Unknown",
        )
    ]
    merged_doc = MergedUnitsDoc(units=units, merged_count=0)
    scenes = [Scene(id="s1", start_ms=0, end_ms=5000, events=[0])]
    characters = [CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN)]

    fake_llm = FakeLLM(
        [
            SceneAnalysisDoc(
                lines={
                    "u1": LineContext(
                        speaker="Yuu Otosaka",
                        listener="Nao Tomori",
                        confidence="high",
                        tone="suspicious",
                        challenges=[],
                    )
                }
            )
        ]
    )

    doc = analyze_scenes(merged_doc, scenes, characters, "Synopsis", fake_llm)
    assert "u1" in doc.lines
    assert doc.lines["u1"].speaker == "Yuu Otosaka"
    assert doc.lines["u1"].confidence == "high"
    assert doc.lines["u1"].tone == "suspicious"


def test_analyze_scenes_fallback_on_llm_failure():
    units = [
        CompositeUnit(
            composite_id="u1",
            unit_ids=["u1"],
            durations_ms=[2000],
            clean_text="Hello.",
            text_with_markers="Hello.",
            speaker="Unknown",
        )
    ]
    merged_doc = MergedUnitsDoc(units=units, merged_count=0)
    fake_llm = FakeLLM(responses={})

    doc = analyze_scenes(merged_doc, [], [], "Synopsis", fake_llm)
    assert "u1" in doc.lines
    assert doc.lines["u1"].confidence == "low"
