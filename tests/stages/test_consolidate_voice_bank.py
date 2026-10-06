from pathlib import Path
from unittest.mock import MagicMock

from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact
from translaterany.media.audio.clustering import cluster_acoustic_segments
from translaterany.media.audio.models import AcousticSegment
from translaterany.media.audio.voice_bank import VoiceBankDoc
from translaterany.memory.models import CharacterEntry
from translaterany.pipeline.stage import StageScope
from translaterany.stages.consolidate_voice_bank import ConsolidateVoiceBankStage


def test_consolidate_voice_bank_stage_metadata() -> None:
    assert ConsolidateVoiceBankStage.name == "consolidate_voice_bank"
    assert ConsolidateVoiceBankStage.scope == StageScope.SERIES
    assert "extract_voice" in ConsolidateVoiceBankStage.inputs


def test_clustering_groups_similar_embeddings() -> None:
    # 2 falas com vetor similar (Falante A) e 2 com vetor diferente (Falante B)
    segs = [
        AcousticSegment("u1", 0, 1000, [1.0, 0.0, 0.0], "male"),
        AcousticSegment("u2", 1000, 2000, [0.95, 0.05, 0.0], "male"),
        AcousticSegment("u3", 2000, 3000, [0.0, 1.0, 0.0], "female"),
        AcousticSegment("u4", 3000, 4000, [0.0, 0.98, 0.02], "female"),
    ]
    clusters = cluster_acoustic_segments(segs, threshold=0.25)
    assert len(clusters) == 2
    # Cada cluster deve ter centróide calculado
    assert len(clusters[0].centroid) == 3
    assert len(clusters[1].centroid) == 3


def test_consolidate_voice_bank_stage_runs_and_creates_voice_bank(tmp_path: Path) -> None:
    stage = ConsolidateVoiceBankStage()
    ctx = MagicMock()

    # 2 episódios com falas da mesma personagem feminina
    ep1_art = VoiceEmbeddingsArtifact(
        episode_id="S01E01",
        segments=[
            AcousticSegment("u1", 0, 1000, [0.0, 1.0, 0.0], "female"),
            AcousticSegment("u2", 1000, 2000, [0.0, 0.99, 0.01], "female"),
        ],
    )
    ep2_art = VoiceEmbeddingsArtifact(
        episode_id="S01E02",
        segments=[
            AcousticSegment("u3", 0, 1000, [0.0, 0.98, 0.02], "female"),
        ],
    )
    ctx.inputs.json_all.return_value = {"S01E01": ep1_art, "S01E02": ep2_art}

    # AniList metadata com uma personagem feminina principal
    char = CharacterEntry(name="Nao Tomori", gender="female", role="main")
    ctx.inputs.json.return_value = MagicMock(characters=[char])
    ctx.output = MagicMock()

    stage.run(ctx)

    assert ctx.output.json.called
    art = ctx.output.json.call_args[0][0]
    assert isinstance(art, VoiceBankDoc)
    assert len(art.profiles) >= 1
    assert art.profiles[0].character_name == "Nao Tomori"
    assert art.profiles[0].canonical_gender == "female"
