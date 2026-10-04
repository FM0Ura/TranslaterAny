"""Reinserção da legenda PT-BR no MKV: temporário oculto, verificação e troca atômica."""

import logging
import os
import shutil
import stat
import subprocess
from pathlib import Path

from translaterany.languages.models import LanguageInfo
from translaterany.languages.registry import LanguageRegistry
from translaterany.media.mkv import MediaError, MkvInfo, probe
from translaterany.media.tracks import OWN_TRACK_NAME, is_own, is_portuguese

SPACE_MARGIN = 1.05
DURATION_TOLERANCE_NS = 1_000_000_000


def temp_path(mkv: Path) -> Path:
    return mkv.with_name(f".{mkv.stem}.translaterany-tmp.mkv")


def build_remux_command(
    mkv: Path,
    ass: Path,
    out: Path | None = None,
    info: MkvInfo | None = None,
    remove_ids: list[int] | None = None,
    target_lang: LanguageInfo | None = None,
) -> list[str]:
    if out is None:
        out = temp_path(mkv)
    if remove_ids is None:
        remove_ids = []

    cmd = ["mkvmerge", "-o", str(out)]
    if remove_ids:
        cmd += ["--subtitle-tracks", "!" + ",".join(str(i) for i in sorted(remove_ids))]
    if info is not None:
        for track in info.subtitles:
            if track.id not in remove_ids:
                cmd += ["--default-track-flag", f"{track.id}:no"]
    cmd.append(str(mkv))

    if target_lang is None or target_lang.code == "pt-BR":
        track_name = OWN_TRACK_NAME
        lang_code = "pt-BR"
    else:
        track_name = f"{target_lang.name_pt.title()} — TranslaterAny"
        lang_code = target_lang.code

    cmd += [
        "--language",
        f"0:{lang_code}",
        "--track-name",
        f"0:{track_name}",
        "--default-track-flag",
        "0:yes",
        str(ass),
    ]
    return cmd


build_command = build_remux_command


def verify(original: MkvInfo, result: MkvInfo, removed: int, target_lang: LanguageInfo | None = None) -> None:
    expected = len(original.tracks) - removed + 1
    if len(result.tracks) != expected:
        raise MediaError(f"verificação do remux falhou: {len(result.tracks)} faixas, esperado {expected}")
    if original.duration_ns and result.duration_ns:
        if abs(original.duration_ns - result.duration_ns) > DURATION_TOLERANCE_NS:
            raise MediaError("verificação do remux falhou: duração diferente da original")
    if len(result.attachments) != len(original.attachments):
        raise MediaError("verificação do remux falhou: anexos (fontes) perdidos")
    defaults = [t for t in result.subtitles if t.default]
    if len(defaults) != 1:
        raise MediaError("verificação do remux falhou: a legenda traduzida não ficou como a única default")
    default_track = defaults[0]
    if target_lang is None or target_lang.code == "pt-BR":
        if not (is_own(default_track) and is_portuguese(default_track)):
            raise MediaError("verificação do remux falhou: a faixa PT-BR não ficou como a única default")
    else:
        if not (is_own(default_track) and LanguageRegistry.matches(default_track.language, target_lang)):
            msg = f"verificação do remux falhou: a faixa {target_lang.name_pt} não ficou como a única default"
            raise MediaError(msg)


def _copy_ownership(source: Path, target: Path) -> None:
    """Mesmo modo e grupo do original (Sonarr/Jellyfin podem depender deles)."""
    st = source.stat()
    os.chmod(target, stat.S_IMODE(st.st_mode))
    try:
        os.chown(target, -1, st.st_gid)
    except OSError:
        pass  # sem permissão para trocar o grupo: mantém o padrão


def _link_or_copy(source: Path, target: Path) -> None:
    try:
        os.link(source, target)  # instantâneo e sem espaço extra; o original segue no lugar
    except OSError:
        shutil.copy2(source, target)


def remux(
    mkv: Path,
    ass: Path,
    *,
    remove_ids: list[int],
    keep_backup: bool,
    log: logging.Logger,
    target_lang: LanguageInfo | None = None,
) -> Path | None:
    """Substitui `mkv` por uma versão com a faixa traduzida. Devolve o caminho do backup, se houver."""
    size = mkv.stat().st_size
    free = shutil.disk_usage(mkv.parent).free
    if free < size * SPACE_MARGIN:
        need = size * SPACE_MARGIN / 1e9
        raise MediaError(f"sem espaço para o remux: precisa de {need:.1f} GB livres em {mkv.parent}")
    original = probe(mkv)
    tmp = temp_path(mkv)
    try:
        cmd = build_remux_command(mkv, ass, tmp, original, remove_ids, target_lang=target_lang)
        result = subprocess.run(
            cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C.UTF-8"}, encoding="utf-8"
        )
        if result.returncode == 1:
            log.warning("mkvmerge terminou com avisos: %s", result.stdout.strip()[-500:])
        elif result.returncode != 0:
            raise MediaError(f"mkvmerge falhou no remux: {result.stdout.strip()[-300:] or result.returncode}")
        verify(original, probe(tmp), len(remove_ids), target_lang=target_lang)
        _copy_ownership(mkv, tmp)
        backup = None
        if keep_backup:
            backup = mkv.with_name(mkv.name + ".bak")
            if not backup.exists():  # o backup guarda sempre o original mais antigo
                _link_or_copy(mkv, backup)
        os.replace(tmp, mkv)
        return backup
    finally:
        tmp.unlink(missing_ok=True)
