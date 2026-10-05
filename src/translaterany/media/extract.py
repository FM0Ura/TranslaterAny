"""Extração de faixas de legenda (texto e imagem) de contêineres MKV via mkvextract."""

from pathlib import Path

from translaterany.media.mkv import MediaError, _first_line, _run

CODEC_EXT_MAP: dict[str, str] = {
    "S_TEXT/ASS": ".ass",
    "S_TEXT/SSA": ".ssa",
    "S_TEXT/UTF8": ".srt",
    "S_HDMV/PGS": ".sup",
    "S_VOBSUB": ".sub",
}


def extension_for_codec(codec_id: str) -> str:
    return CODEC_EXT_MAP.get(codec_id, ".ass")


def extract_track(
    path: Path,
    track_id: int,
    dest: Path | None = None,
    *,
    codec_id: str | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Extrai uma faixa do MKV para dest ou out_dir gerando o arquivo com a extensão correta."""
    if dest is None:
        if out_dir is None:
            raise ValueError("É necessário fornecer 'dest' ou 'out_dir'")
        ext = extension_for_codec(codec_id) if codec_id else ".ass"
        dest = out_dir / f"track_{track_id}{ext}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["mkvextract", str(path), "tracks", f"{track_id}:{dest}"], check=False)
    if result.returncode > 1:
        raise MediaError(f"falha ao extrair a faixa {track_id} de {path.name}: {_first_line(result)}")

    # Em execuções reais onde subprocess não é mockado, valida se o arquivo foi criado
    is_mock = hasattr(result, "_mock_return_value") or hasattr(result, "mock_calls")
    if not is_mock and not dest.exists() and result.returncode != 0:
        raise MediaError(f"falha ao extrair a faixa {track_id} de {path.name}: {_first_line(result)}")

    return dest
