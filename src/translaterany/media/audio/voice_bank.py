"""Modelos de dados para o banco de vozes da série (voice_bank.json)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VoiceProfile(BaseModel):
    """Perfil acústico de um personagem na série."""

    character_name: str
    canonical_gender: Literal["male", "female", "unknown"] = "unknown"
    centroid: list[float] = Field(default_factory=list)
    sample_count: int = 0
    confidence: Literal["high", "medium", "low"] = "high"


class VoiceBankDoc(BaseModel):
    """Documento da série contendo todos os perfis consolidados de voz."""

    profiles: list[VoiceProfile] = Field(default_factory=list)
