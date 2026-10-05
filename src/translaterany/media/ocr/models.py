"""Modelos de dados para OCR de legendas gráficas."""

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class SubtitleDisplaySet:
    start_ms: int
    end_ms: int
    x: int
    y: int
    width: int
    height: int
    video_width: int
    video_height: int
    image: Image.Image  # Modo L (grayscale binarizado)
    forced: bool = False
