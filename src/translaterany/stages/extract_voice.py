"""Etapa extract_voice: extração de áudio vocal e geração de voice_embeddings.json por episódio."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact
from translaterany.media.audio.engine import create_diarization_engine
from translaterany.media.audio.extractor import AudioExtractor
from translaterany.media.audio.models import UnitTiming
from translaterany.media.mkv import MediaError, probe
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.normalize import NormalizedDoc

logger = logging.getLogger(__name__)


@register_stage
class ExtractVoiceStage(Stage):
    """Etapa por episódio que extrai o áudio correspondente do MKV e produz voice_embeddings.json."""

    name: ClassVar[str] = "extract_voice"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    inputs: ClassVar[tuple[str, ...]] = ("normalize",)
    translates: ClassVar[bool] = False
    enabled_by_default: ClassVar[bool] = True

    def _find_audio_track_index(self, mkv_path: Path) -> int | None:
        """Encontra o índice relativo da primeira faixa de áudio vocal no MKV."""
        try:
            info = probe(mkv_path)
            audio_tracks = [t for t in info.tracks if t.type == "audio"]
            if not audio_tracks:
                return None
            # Retorna o índice ordinal de áudio (para uso no -map 0:a:<idx>)
            return 0
        except (MediaError, Exception) as exc:
            logger.debug("Não foi possível identificar faixas de áudio em %s: %s", mkv_path, exc)
            return None

    def run(self, ctx: StageContext) -> None:
        norm_doc = ctx.inputs.json("normalize", NormalizedDoc)
        mkv_path = Path(ctx.episode.source) if ctx.episode and ctx.episode.source else None

        ep_key = str(ctx.episode.key) if ctx.episode and ctx.episode.key else ""
        if not mkv_path or not mkv_path.exists():
            logger.info("Arquivo de vídeo não encontrado para %s. Gerando embeddings vazios.", ep_key)
            ctx.output.json(
                VoiceEmbeddingsArtifact(
                    episode_id=ep_key,
                    segments=[],
                    audio_track_found=False,
                )
            )
            return

        track_idx = self._find_audio_track_index(mkv_path)
        if track_idx is None:
            logger.info("Nenhuma faixa de áudio encontrada no MKV para %s.", mkv_path.name)
            ctx.output.json(
                VoiceEmbeddingsArtifact(
                    episode_id=ep_key,
                    segments=[],
                    audio_track_found=False,
                )
            )
            return

        # Coleta os carimbos de tempo de cada fala normalizada a partir dos eventos
        timings: list[UnitTiming] = []
        for ev in norm_doc.events:
            if ev.unit and ev.end_ms > ev.start_ms:
                timings.append(UnitTiming(unit_id=ev.unit, start_ms=ev.start_ms, end_ms=ev.end_ms))

        engine_name = "onnx"
        hf_token = None
        if ctx.config:
            # Obtém opções configuradas se houver
            opts = getattr(ctx.config, "stages_options", {}).get("extract_voice", {})
            engine_name = opts.get("engine", "onnx")
            hf_token = opts.get("hf_token")

        engine = create_diarization_engine(engine_name=engine_name, hf_token=hf_token)
        extractor = AudioExtractor()

        try:
            with extractor.extract_voice_track(mkv_path, track_index=track_idx) as wav_path:
                segments = engine.extract_embeddings(wav_path, timings)
        except Exception as exc:
            logger.warning("Falha durante a extração/diarização de áudio para %s: %s", mkv_path.name, exc)
            segments = []

        art = VoiceEmbeddingsArtifact(
            episode_id=ep_key,
            segments=segments,
            audio_track_found=True,
        )
        ctx.output.json(art)
