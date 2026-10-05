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


def test_build_known_names_prioritizes_main_character():
    from translaterany.subtitles.scene_analysis import _build_known_names

    chars = [
        CharacterEntry(name="Souichirou Takagi", gender=Gender.MALE, role=CharacterRole.SUPPORTING),
        CharacterEntry(name="Saya Takagi", gender=Gender.FEMALE, role=CharacterRole.MAIN),
        CharacterEntry(name="Takashi Komuro", gender=Gender.MALE, role=CharacterRole.MAIN, aliases=["Taka"]),
    ]
    known = _build_known_names(chars)
    assert known["takagi"] == "Saya Takagi"
    assert known["saya"] == "Saya Takagi"
    assert known["takashi"] == "Takashi Komuro"
    assert known["komuro"] == "Takashi Komuro"
    assert known["taka"] == "Takashi Komuro"
    assert known["souichirou"] == "Souichirou Takagi"


def test_extract_vocative():
    from translaterany.subtitles.scene_analysis import _extract_vocative

    known = {"takagi": "Saya Takagi", "takashi": "Takashi Komuro", "hirano": "Kouta Hirano"}
    assert _extract_vocative("Takagi, why do you always dis me like that?", known) == "Saya Takagi"
    assert _extract_vocative("You wouldn't understand, Takashi.", known) == "Takashi Komuro"
    assert _extract_vocative("Hirano!", known) == "Kouta Hirano"
    assert _extract_vocative("Because I don't like stupid people.", known) is None


def test_analyze_scenes_vocative_safeguard_swaps_inverted_speaker():
    units = [
        CompositeUnit(
            composite_id="u51",
            unit_ids=["u51"],
            durations_ms=[3000],
            clean_text="Takagi, why do you always dis me like that?",
            text_with_markers="Takagi, why do you always dis me like that?",
            speaker="Unknown",
        )
    ]
    merged_doc = MergedUnitsDoc(units=units, merged_count=0)
    scenes = [Scene(id="s1", start_ms=0, end_ms=5000, events=[0])]
    characters = [
        CharacterEntry(name="Saya Takagi", gender=Gender.FEMALE, role=CharacterRole.MAIN),
        CharacterEntry(name="Takashi Komuro", gender=Gender.MALE, role=CharacterRole.MAIN),
    ]

    # Model mistakenly inverted speaker and listener
    fake_llm = FakeLLM(
        [
            SceneAnalysisDoc(
                lines={
                    "u51": LineContext(
                        speaker="Saya Takagi",
                        listener="Takashi Komuro",
                        confidence="high",
                        tone="annoyed",
                        challenges=[],
                    )
                }
            )
        ]
    )

    doc = analyze_scenes(merged_doc, scenes, characters, "Synopsis", fake_llm)
    assert doc.lines["u51"].speaker == "Takashi Komuro"
    assert doc.lines["u51"].listener == "Saya Takagi"


def test_analyze_scenes_vocative_safeguard_sets_listener_when_unknown():
    units = [
        CompositeUnit(
            composite_id="u36",
            unit_ids=["u36"],
            durations_ms=[2000],
            clean_text="You wouldn't understand, Takashi.",
            text_with_markers="You wouldn't understand, Takashi.",
            speaker="Unknown",
        )
    ]
    merged_doc = MergedUnitsDoc(units=units, merged_count=0)
    scenes = [Scene(id="s1", start_ms=0, end_ms=5000, events=[0])]
    characters = [
        CharacterEntry(name="Rei Miyamoto", gender=Gender.FEMALE, role=CharacterRole.MAIN),
        CharacterEntry(name="Takashi Komuro", gender=Gender.MALE, role=CharacterRole.MAIN),
    ]

    fake_llm = FakeLLM(
        [
            SceneAnalysisDoc(
                lines={
                    "u36": LineContext(
                        speaker="Rei Miyamoto",
                        listener="Unknown",
                        confidence="high",
                        tone="dismissive",
                        challenges=[],
                    )
                }
            )
        ]
    )

    doc = analyze_scenes(merged_doc, scenes, characters, "Synopsis", fake_llm)
    assert doc.lines["u36"].speaker == "Rei Miyamoto"
    assert doc.lines["u36"].listener == "Takashi Komuro"

