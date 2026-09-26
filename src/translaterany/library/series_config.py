"""Leitura do series.toml opcional (a app só lê; o usuário cria)."""

import tomllib
from pathlib import Path

from pydantic import ValidationError

from translaterany.pipeline.units import LINE_TYPES, SeriesConfig

FILENAME = "series.toml"


class SeriesConfigError(Exception):
    """series.toml inválido. Mensagem pronta para o usuário."""


def load_series_config(root: Path) -> SeriesConfig:
    path = root / FILENAME
    if not path.is_file():
        return SeriesConfig()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
        raise SeriesConfigError(f"{path}: arquivo inválido — {exc}") from exc
    unknown = set(raw) - {"subtitles", "styles"}
    if unknown:
        raise SeriesConfigError(f"{path}: seção desconhecida {sorted(unknown)} (use [subtitles] e [styles])")
    subtitles = raw.get("subtitles", {})
    styles = raw.get("styles", {})
    if not isinstance(subtitles, dict) or set(subtitles) - {"track"}:
        raise SeriesConfigError(f"{path}: [subtitles] aceita apenas 'track'")
    for style, kind in styles.items() if isinstance(styles, dict) else []:
        if kind not in LINE_TYPES:
            raise SeriesConfigError(f'{path}: [styles] "{style}" = "{kind}"; use um de {", ".join(LINE_TYPES)}')
    try:
        return SeriesConfig(track=subtitles.get("track"), styles=styles)
    except ValidationError as exc:
        raise SeriesConfigError(f"{path}: {exc.errors()[0]['msg']}") from exc
