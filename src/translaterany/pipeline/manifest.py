"""Manifest: registro, por unidade (série ou episódio), do que cada etapa já produziu."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from translaterany.util.fs import atomic_write_text

MANIFEST_SCHEMA = 1

type UnitStatus = Literal["ok", "skipped", "failed"]


class ManifestError(Exception):
    """Manifest ilegível ou de versão desconhecida."""


class StageRecord(BaseModel):
    status: Literal["done", "failed"]
    key: str | None = None
    artifact: str | None = None
    artifact_hash: str | None = None
    started_at: datetime
    finished_at: datetime
    duration_s: float
    error: str | None = None


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
    if manifest.schema_version != MANIFEST_SCHEMA:
        raise ManifestError(
            f"manifest em {path} tem schema {manifest.schema_version}; "
            f"esta versão entende apenas o schema {MANIFEST_SCHEMA}"
        )
    return manifest


def save_manifest(path: Path, manifest: Manifest) -> None:
    atomic_write_text(path, manifest.model_dump_json(by_alias=True, indent=2))
