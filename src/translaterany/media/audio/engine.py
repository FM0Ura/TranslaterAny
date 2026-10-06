"""Protocolo e fábrica de motores de diarização de áudio."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from translaterany.media.audio.models import AcousticSegment, UnitTiming

logger = logging.getLogger(__name__)


class DiarizationEngine(Protocol):
    """Interface padrão para motores de extração de embeddings e diarização acústica."""

    def extract_embeddings(
        self,
        audio_path: Path,
        timings: list[UnitTiming],
    ) -> list[AcousticSegment]:
        """Extrai vetores acústicos e classificação de gênero para cada intervalo de fala."""
        ...


def create_diarization_engine(
    engine_name: str = "onnx",
    hf_token: str | None = None,
) -> DiarizationEngine:
    """Cria uma instância de DiarizationEngine com base na configuração e credenciais disponíveis."""
    norm_name = engine_name.lower().strip()

    if norm_name == "pyannote":
        token = hf_token or os.environ.get("HF_TOKEN")
        if not token:
            logger.warning(
                "HF_TOKEN ausente no ambiente/configuração para o motor PyAnnote. "
                "Fazendo fallback automático para o motor padrão ONNX livre."
            )
            from translaterany.media.audio.onnx_engine import OnnxAudioDiarizer

            return OnnxAudioDiarizer()

        from translaterany.media.audio.pyannote_engine import PyAnnoteAudioDiarizer

        return PyAnnoteAudioDiarizer(hf_token=token)

    from translaterany.media.audio.onnx_engine import OnnxAudioDiarizer

    return OnnxAudioDiarizer()
