"""Artefatos serializáveis para o subsistema de áudio."""

from __future__ import annotations

from pydantic import BaseModel, Field

from translaterany.media.audio.models import AcousticSegment


class VoiceEmbeddingsArtifact(BaseModel):
    """Artefato voice_embeddings.json gerado por episódio com os vetores acústicos das falas."""

    episode_id: str = ""
    segments: list[AcousticSegment] = Field(default_factory=list)
    audio_track_found: bool = True
