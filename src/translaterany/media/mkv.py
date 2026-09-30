"""Leitura de metadados (mkvmerge -J, independente de idioma) e extração de faixas (mkvextract)."""

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEXT_CODECS = frozenset({"S_TEXT/ASS", "S_TEXT/SSA", "S_TEXT/UTF8"})
IMAGE_CODECS = frozenset({"S_HDMV/PGS", "S_VOBSUB"})


class MediaError(Exception):
    """Falha ao ler ou processar um MKV. Mensagem pronta para o usuário."""


@dataclass(frozen=True)
class Track:
    id: int
    type: str  # video | audio | subtitles
    codec_id: str
    language: str  # IETF quando disponível (ex.: "en", "pt-BR"), senão ISO 639-2
    name: str
    default: bool
    forced: bool
    hearing_impaired: bool


@dataclass(frozen=True)
class Attachment:
    id: int
    file_name: str
    content_type: str


@dataclass(frozen=True)
class MkvInfo:
    tracks: tuple[Track, ...]
    attachments: tuple[Attachment, ...]
    duration_ns: int | None

    @property
    def subtitles(self) -> list[Track]:
        return [t for t in self.tracks if t.type == "subtitles"]


def parse_identify(data: dict[str, Any]) -> MkvInfo:
    """Converte a saída JSON do `mkvmerge -J`."""
    tracks = []
    for raw in data.get("tracks", []):
        props = raw.get("properties", {})
        tracks.append(
            Track(
                id=int(raw["id"]),
                type=raw.get("type", ""),
                codec_id=props.get("codec_id", ""),
                language=props.get("language_ietf") or props.get("language", "und"),
                name=props.get("track_name", ""),
                default=bool(props.get("default_track", False)),
                forced=bool(props.get("forced_track", False)),
                hearing_impaired=bool(props.get("flag_hearing_impaired", False)),
            )
        )
    attachments = tuple(
        Attachment(id=int(a["id"]), file_name=a.get("file_name", ""), content_type=a.get("content_type", ""))
        for a in data.get("attachments", [])
    )
    duration = data.get("container", {}).get("properties", {}).get("duration")
    return MkvInfo(tracks=tuple(tracks), attachments=attachments, duration_ns=int(duration) if duration else None)


def probe(path: Path) -> MkvInfo:
    result = _run(["mkvmerge", "-J", str(path)])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"MKV ilegível: resposta inesperada do mkvmerge para {path.name}") from exc
    if not data.get("container", {}).get("recognized", False) or data.get("errors"):
        detail = (data.get("errors") or ["formato não reconhecido"])[0]
        raise MediaError(f"MKV ilegível: {detail}")
    return parse_identify(data)


def extract_track(path: Path, track_id: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["mkvextract", str(path), "tracks", f"{track_id}:{dest}"], check=False)
    if result.returncode > 1 or not dest.exists():
        raise MediaError(f"falha ao extrair a faixa {track_id} de {path.name}: {_first_line(result)}")


_FONT_MIMES = frozenset(
    {"application/x-truetype-font", "application/vnd.ms-opentype", "application/font-sfnt", "application/x-font-ttf"}
)
_FONT_EXTS = (".ttf", ".otf", ".ttc")


def font_attachments(info: MkvInfo) -> list[Attachment]:
    return [
        a
        for a in info.attachments
        if a.content_type.startswith("font/")
        or a.content_type in _FONT_MIMES
        or a.file_name.lower().endswith(_FONT_EXTS)
    ]


def extract_attachments(path: Path, attachments: Sequence[Attachment], dest_dir: Path) -> list[Path]:
    """Extrai anexos para dest_dir como '<id>-<nome>'. Devolve os arquivos que de fato existem."""
    if not attachments:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    targets = {a.id: dest_dir / f"{a.id}-{Path(a.file_name).name or 'font'}" for a in attachments}
    result = _run(["mkvextract", str(path), "attachments", *(f"{i}:{p}" for i, p in targets.items())], check=False)
    if result.returncode > 1:
        raise MediaError(f"falha ao extrair anexos de {path.name}: {_first_line(result)}")
    return [p for p in targets.values() if p.exists()]


def tool_available(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    if tool_available(cmd[0]) is None:
        raise MediaError(f"{cmd[0]} não encontrado no PATH (instale o MKVToolNix)")
    result = subprocess.run(
        cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C.UTF-8"}, encoding="utf-8"
    )
    if check and result.returncode > 1:
        raise MediaError(f"MKV ilegível: {_first_line(result)}")
    return result


def _first_line(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stdout or "") + (result.stderr or "")
    return next((line.strip() for line in text.splitlines() if line.strip()), f"código {result.returncode}")
