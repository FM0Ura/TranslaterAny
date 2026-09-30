"""Modelos das checagens: entrada por linha, ambiente do episódio e achados."""

from typing import Literal

from pydantic import BaseModel, Field

from translaterany.config.model import ChecksConfig
from translaterany.memory.models import GlossaryEntry

type Severity = Literal["info", "warn", "error"]


class LineInput(BaseModel):
    id: str  # id da unidade ou id composto ("u1+u2")
    line_type: str
    style: str = ""
    source: str  # EN com marcadores ⟦n⟧
    target: str  # PT-BR com marcadores ⟦n⟧
    duration_ms: int = 0
    composite: bool = False  # id composto: nunca exibido como uma linha só (sem CPL/linhas)


class CheckEnv(BaseModel):
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    names: list[list[str]] = Field(default_factory=list)  # nome + aliases de cada personagem
    limits: ChecksConfig = Field(default_factory=ChecksConfig)


class Finding(BaseModel):
    check: str
    unit_id: str | None = None  # None em checagens de episódio
    severity: Severity
    message: str
    value: float | None = None
    excerpt: str | None = None  # trecho do PT (só no estado final)
