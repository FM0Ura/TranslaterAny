"""Utilitários de sistema de arquivos: escrita atômica, slugs e hashing."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

TMP_MARKER = ".tmp-"
_MIB = 1024 * 1024
_NON_ALNUM = re.compile(r"[\W_]+")


def slugify(name: str) -> str:
    """Slug estável e seguro para nomes de diretório, com sufixo de hash contra colisões."""
    base = _NON_ALNUM.sub("-", name.lower()).strip("-") or "x"
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
    return f"{base}-{suffix}"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_MIB), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def fingerprint(path: Path) -> str:
    """Impressão digital barata de arquivos grandes: tamanho + primeiro MiB + último MiB."""
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as fh:
        digest.update(fh.read(_MIB))
        if size > _MIB:
            fh.seek(max(size - _MIB, _MIB))
            digest.update(fh.read(_MIB))
    return "sha256:" + digest.hexdigest()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    """Grava num temporário no mesmo diretório e renomeia: o arquivo final nunca fica parcial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}{TMP_MARKER}{os.getpid()}")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write(path, text.encode("utf-8"))


def cleanup_tmp(directory: Path) -> int:
    """Remove temporários deixados por execuções interrompidas. Retorna quantos removeu."""
    if not directory.exists():
        return 0
    removed = 0
    for tmp in directory.rglob(f"*{TMP_MARKER}*"):
        if tmp.is_file():
            tmp.unlink()
            removed += 1
    return removed
