"""Manifest: registro, por unidade (série ou episódio), do que cada etapa já produziu."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from translaterany.llm.metered import LLMStats
from translaterany.util.fs import atomic_write_text

MANIFEST_SCHEMA = 2
_READABLE_SCHEMAS = frozenset({1, 2})  # schema 1 (até o M4) só não tem llm/counters

type UnitStatus = Literal["ok", "skipped", "failed"]


class ManifestError(Exception):
    """Manifest ilegível ou de versão desconhecida."""


class StageRecord(BaseModel):
    status: Literal["done", "failed"]
    key: str | None = None
    artifact: str | None = None
    artifact_hash: str | None = None
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime = Field(default_factory=datetime.now)
    duration_s: float = 0.0
    error: str | None = None
    llm: LLMStats | None = None
    counters: dict[str, int] = Field(default_factory=dict)


class UnitInfo(BaseModel):
    series: str
    episode: str | None = None
    source: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=MANIFEST_SCHEMA, alias="schema")
    unit: UnitInfo
    status: UnitStatus = "ok"
    skip_reason: str | None = None
    stages: dict[str, StageRecord] = Field(default_factory=dict)


def load_manifest(path: Path, unit: UnitInfo) -> Manifest:
    """Lê o manifest; se não existir, devolve um novo (vazio) para a unidade."""
    if not path.exists():
        return Manifest(unit=unit)
    try:
        manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, UnicodeDecodeError, OSError) as exc:
        raise ManifestError(f"manifest inválido em {path}: {exc}") from exc
    if manifest.schema_version not in _READABLE_SCHEMAS:
        raise ManifestError(
            f"manifest em {path} tem schema {manifest.schema_version}; "
            f"esta versão entende os schemas {', '.join(map(str, sorted(_READABLE_SCHEMAS)))}"
        )
    manifest.schema_version = MANIFEST_SCHEMA  # o próximo save grava no formato atual
    return manifest


def save_manifest(path: Path, manifest: Manifest) -> None:
    atomic_write_text(path, manifest.model_dump_json(by_alias=True, indent=2))


EpisodeManifest = Manifest


def __getattr__(name: str):
    if name == "ManifestSet":
        from translaterany.pipeline.artifacts import ManifestSet

        return ManifestSet
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
