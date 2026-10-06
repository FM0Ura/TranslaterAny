"""Teste de integração ponta a ponta do subsistema multimodal de áudio (M11 - v1.2)."""

from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact
from translaterany.media.audio.models import AcousticSegment
from translaterany.media.audio.voice_bank import VoiceBankDoc, VoiceProfile
from translaterany.memory.models import CharacterEntry
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.scene_analysis import SceneAnalysisStage
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import analyze_scenes_multimodal


def test_m11_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert i("normalize") < i("extract_voice")
    assert i("extract_voice") < i("consolidate_voice_bank")
    assert i("consolidate_voice_bank") < i("scene_analysis")


def test_m11_scene_analysis_stage_inputs() -> None:
    from translaterany.stages.consolidate_voice_bank import ConsolidateVoiceBankStage
    from translaterany.stages.extract_voice import ExtractVoiceStage

    stage = SceneAnalysisStage()
    assert "merge_sentences" in stage.inputs
    assert "extract_voice" not in stage.inputs

    stage.bind_pipeline([ExtractVoiceStage(), ConsolidateVoiceBankStage()], None)
    assert "extract_voice" in stage.inputs
    assert "consolidate_voice_bank" in stage.inputs


def test_m11_multimodal_pipeline_synthetic_flow() -> None:
    # 1. Simula artefato extract_voice do episódio
    ep_voice = VoiceEmbeddingsArtifact(
        episode_id="S01E01",
        segments=[
            AcousticSegment(
                unit_id="u1",
                start_ms=1000,
                end_ms=3000,
                embedding=[1.0, 0.0, 0.0],
                acoustic_gender="female",
            ),
            AcousticSegment(
                unit_id="u2",
                start_ms=4000,
                end_ms=6000,
                embedding=[0.0, 1.0, 0.0],
                acoustic_gender="male",
            ),
        ],
        audio_track_found=True,
    )

    # 2. Simula voice_bank.json da série consolidada
    voice_bank = VoiceBankDoc(
        profiles=[
            VoiceProfile(
                character_name="Nao Tomori",
                canonical_gender="female",
                centroid=[0.99, 0.01, 0.0],
                sample_count=80,
                confidence="high",
            ),
            VoiceProfile(
                character_name="Yuu Otosaka",
                canonical_gender="male",
                centroid=[0.0, 0.99, 0.01],
                sample_count=120,
                confidence="high",
            ),
        ]
    )

    # 3. Unidades de diálogo da cena
    u1 = CompositeUnit(
        composite_id="u1",
        unit_ids=["u1"],
        durations_ms=[2000],
        clean_text="Eu vou pegar a câmera.",
        text_with_markers="Eu vou pegar a câmera.",
    )
    u2 = CompositeUnit(
        composite_id="u2",
        unit_ids=["u2"],
        durations_ms=[2000],
        clean_text="Tudo bem, Tomori.",
        text_with_markers="Tudo bem, Tomori.",
    )
    merged_doc = MergedUnitsDoc(units=[u1, u2])

    scenes = [Scene(id="0", start_ms=0, end_ms=10000, events=[0, 1])]
    characters = [
        CharacterEntry(name="Nao Tomori", gender="female", role="main"),
        CharacterEntry(name="Yuu Otosaka", gender="male", role="main"),
    ]

    segments_map = {s.unit_id: s for s in ep_voice.segments}

    # 4. Executa análise multimodal
    result = analyze_scenes_multimodal(
        merged_doc=merged_doc,
        scenes=scenes,
        characters=characters,
        voice_bank=voice_bank,
        episode_segments=segments_map,
    )

    # u1: Centróide bate com Nao Tomori -> speaker Nao Tomori, confidence high
    assert result.lines["u1"].speaker == "Nao Tomori"
    assert result.lines["u1"].confidence == "high"

    # u2: Centróide bate com Yuu Otosaka, vocativo interpela "Tomori" -> speaker Yuu Otosaka, listener Tomori
    assert result.lines["u2"].speaker == "Yuu Otosaka"
    assert result.lines["u2"].listener == "Nao Tomori"
    assert result.lines["u2"].confidence == "high"
