"""Contrato das etapas de texto: {id da unidade: texto com marcadores ⟦n⟧}."""

from pydantic import BaseModel, Field


class UnitTexts(BaseModel):
    texts: dict[str, str] = Field(default_factory=dict)
    used_terms: dict[str, str] = Field(default_factory=dict)
