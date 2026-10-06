from translaterany.media.audio.models import AcousticSegment
from translaterany.media.audio.voice_bank import VoiceBankDoc, VoiceProfile
from translaterany.memory.models import CharacterEntry
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import analyze_scenes_multimodal


def test_multimodal_assigns_speaker_from_voice_centroid() -> None:
    chars = [CharacterEntry(name="Yuu Otosaka", gender="male", role="main")]
    voice_bank = VoiceBankDoc(
        profiles=[
            VoiceProfile(
                character_name="Yuu Otosaka",
                canonical_gender="male",
                centroid=[1.0, 0.0, 0.0],
                sample_count=50,
                confidence="high",
            )
        ]
    )
    unit = CompositeUnit(
        composite_id="u1",
        unit_ids=["u1"],
        durations_ms=[1000],
        clean_text="Sim, eu concordo.",
        text_with_markers="Sim, eu concordo.",
    )
    merged_doc = MergedUnitsDoc(units=[unit])
    segments = {
        "u1": AcousticSegment("u1", 1000, 2000, [0.98, 0.02, 0.0], "male")
    }

    result = analyze_scenes_multimodal(
        merged_doc=merged_doc,
        scenes=[Scene(id="0", start_ms=0, end_ms=5000, events=[0])],
        characters=chars,
        voice_bank=voice_bank,
        episode_segments=segments,
    )

    ctx = result.lines["u1"]
    assert ctx.speaker == "Yuu Otosaka"
    assert ctx.confidence == "high"


def test_multimodal_vocative_guard_prevents_addressed_character_as_speaker() -> None:
    chars = [
        CharacterEntry(name="Yuu Otosaka", gender="male", role="main"),
        CharacterEntry(name="Nao Tomori", gender="female", role="main"),
    ]
    # Fala diz "Yuu, cuidado!" -> quem fala NÃO pode ser o Yuu
    unit = CompositeUnit(
        composite_id="u1",
        unit_ids=["u1"],
        durations_ms=[1000],
        clean_text="Yuu, cuidado!",
        text_with_markers="Yuu, cuidado!",
    )
    merged_doc = MergedUnitsDoc(units=[unit])
    segments = {
        "u1": AcousticSegment("u1", 1000, 2000, [0.95, 0.05, 0.0], "female")
    }
    voice_bank = VoiceBankDoc(
        profiles=[
            VoiceProfile(
                character_name="Yuu Otosaka",
                canonical_gender="male",
                centroid=[0.95, 0.05, 0.0],
                sample_count=50,
                confidence="high",
            ),
            VoiceProfile(
                character_name="Nao Tomori",
                canonical_gender="female",
                centroid=[0.0, 1.0, 0.0],
                sample_count=40,
                confidence="high",
            ),
        ]
    )
    result = analyze_scenes_multimodal(
        merged_doc=merged_doc,
        scenes=[Scene(id="0", start_ms=0, end_ms=5000, events=[0])],
        characters=chars,
        voice_bank=voice_bank,
        episode_segments=segments,
    )
    assert result.lines["u1"].speaker != "Yuu Otosaka"
    assert result.lines["u1"].listener == "Yuu Otosaka"
