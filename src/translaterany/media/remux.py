"""Reinserção da legenda PT-BR no MKV: temporário oculto, verificação e troca atômica."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from translaterany.media.mkv import MediaError, MkvInfo, probe
from translaterany.media.tracks import OWN_TRACK_NAME, is_own, is_portuguese

SPACE_MARGIN = 1.05
DURATION_TOLERANCE_NS = 1_000_000_000


def temp_path(mkv: Path) -> Path:
    return mkv.with_name(f".{mkv.stem}.translaterany-tmp.mkv")


def build_command(mkv: Path, ass: Path, out: Path, info: MkvInfo, remove_ids: list[int]) -> list[str]:
    cmd = ["mkvmerge", "-o", str(out)]
    if remove_ids:
        cmd += ["--subtitle-tracks", "!" + ",".join(str(i) for i in sorted(remove_ids))]
    for track in info.subtitles:
        if track.id not in remove_ids:
            cmd += ["--default-track-flag", f"{track.id}:no"]
    cmd.append(str(mkv))
    cmd += ["--language", "0:pt-BR", "--track-name", f"0:{OWN_TRACK_NAME}", "--default-track-flag", "0:yes", str(ass)]
    return cmd


def verify(original: MkvInfo, result: MkvInfo, removed: int) -> None:
    expected = len(original.tracks) - removed + 1
    if len(result.tracks) != expected:
        raise MediaError(f"verificação do remux falhou: {len(result.tracks)} faixas, esperado {expected}")
    if original.duration_ns and result.duration_ns:
        if abs(original.duration_ns - result.duration_ns) > DURATION_TOLERANCE_NS:
            raise MediaError("verificação do remux falhou: duração diferente da original")
    if len(result.attachments) != len(original.attachments):
        raise MediaError("verificação do remux falhou: anexos (fontes) perdidos")
    defaults = [t for t in result.subtitles if t.default]
    if len(defaults) != 1 or not (is_own(defaults[0]) and is_portuguese(defaults[0])):
        raise MediaError("verificação do remux falhou: a faixa PT-BR não ficou como a única default")


def remux(
    mkv: Path,
    ass: Path,
    *,
    remove_ids: list[int],
    keep_backup: bool,
    log: logging.Logger,
) -> Path | None:
    """Substitui `mkv` por uma versão com a faixa PT-BR. Devolve o caminho do backup, se houver."""
    size = mkv.stat().st_size
    free = shutil.disk_usage(mkv.parent).free
    if free < size * SPACE_MARGIN:
        need = size * SPACE_MARGIN / 1e9
        raise MediaError(f"sem espaço para o remux: precisa de {need:.1f} GB livres em {mkv.parent}")
    original = probe(mkv)
    tmp = temp_path(mkv)
    try:
        cmd = build_command(mkv, ass, tmp, original, remove_ids)
        result = subprocess.run(
            cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C.UTF-8"}, encoding="utf-8"
        )
        if result.returncode == 1:
            log.warning("mkvmerge terminou com avisos: %s", result.stdout.strip()[-500:])
        elif result.returncode != 0:
            raise MediaError(f"mkvmerge falhou no remux: {result.stdout.strip()[-300:] or result.returncode}")
        verify(original, probe(tmp), len(remove_ids))
        backup = None
        if keep_backup:
            backup = mkv.with_name(mkv.name + ".bak")
            os.replace(mkv, backup)
        os.replace(tmp, mkv)
        return backup
    finally:
        tmp.unlink(missing_ok=True)
