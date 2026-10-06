"""Modelos de dados para o subsistema de áudio e diarização."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class UnitTiming:
    """Carimbos de tempo de um segmento de legenda."""

    unit_id: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


@dataclass(frozen=True)
class AcousticSegment:
    """Informações acústicas extraídas de um segmento de fala."""

    unit_id: str
    start_ms: int
    end_ms: int
    embedding: list[float] = field(default_factory=list)
    acoustic_gender: Literal["male", "female", "unknown"] = "unknown"
    has_speech: bool = True
    is_overlapped: bool = False
