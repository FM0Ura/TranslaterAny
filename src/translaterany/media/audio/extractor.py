"""Extração de faixa vocal leve em WAV a partir de arquivo MKV usando ffmpeg."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioExtractor:
    """Extrai canais de áudio vocal com ffmpeg em formato mono 16kHz WAV."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    @contextlib.contextmanager
    def extract_voice_track(
        self,
        mkv_path: Path,
        track_index: int = 0,
    ) -> Generator[Path]:
        """Extrai a faixa de áudio vocal correspondente do MKV para um WAV mono temporário.
        Remove o arquivo ao final do bloco context manager.
        """
        temp_dir = tempfile.gettempdir()
        temp_wav = Path(temp_dir) / f"translaterany_voice_{mkv_path.stem}_{track_index}.wav"

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(mkv_path),
            "-map",
            f"0:a:{track_index}",
            "-ac",
            "1",
            "-ar",
            str(self.sample_rate),
            "-vn",
            "-sn",
            str(temp_wav),
        ]

        logger.debug("Executando extração de áudio: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.warning("Falha ao extrair áudio com ffmpeg: %s", proc.stderr.strip())

        try:
            yield temp_wav
        finally:
            if temp_wav.exists():
                with contextlib.suppress(Exception):
                    temp_wav.unlink()
