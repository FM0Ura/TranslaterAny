"""Leitura do series.toml opcional (a app só lê; o usuário cria)."""

import tomllib
from pathlib import Path

from pydantic import ValidationError

from translaterany.pipeline.units import LINE_TYPES, SeriesConfig, SeriesMetadataConfig

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
    unknown = set(raw) - {"subtitles", "styles", "metadata", "languages", "source_language", "target_language"}
    if unknown:
        raise SeriesConfigError(
            f"{path}: seção desconhecida {sorted(unknown)} (use [subtitles], [styles], [metadata] e [languages])"
        )
    languages_raw = raw.get("languages", {})
    if not isinstance(languages_raw, dict):
        raise SeriesConfigError(f"{path}: [languages] deve ser uma tabela")
    src_lang = raw.get("source_language") or languages_raw.get("source") or languages_raw.get("source_language")
    tgt_lang = raw.get("target_language") or languages_raw.get("target") or languages_raw.get("target_language")

    subtitles = raw.get("subtitles", {})
    styles = raw.get("styles", {})
    metadata_raw = raw.get("metadata", {})
    if not isinstance(subtitles, dict) or set(subtitles) - {"track"}:
        raise SeriesConfigError(f"{path}: [subtitles] aceita apenas 'track'")
    for style, kind in styles.items() if isinstance(styles, dict) else []:
        if kind not in LINE_TYPES:
            raise SeriesConfigError(f'{path}: [styles] "{style}" = "{kind}"; use um de {", ".join(LINE_TYPES)}')
    if not isinstance(metadata_raw, dict) or set(metadata_raw) - {"anilist_id"}:
        raise SeriesConfigError(f"{path}: [metadata] aceita apenas 'anilist_id'")
    metadata_config = SeriesMetadataConfig()
    if "metadata" in raw:
        raw_id = metadata_raw.get("anilist_id")
        if raw_id is not None:
            if isinstance(raw_id, bool) or not isinstance(raw_id, int):
                raise SeriesConfigError(f"{path}: [metadata] anilist_id deve ser um número inteiro")
            if raw_id <= 0:
                raise SeriesConfigError(f"{path}: [metadata] anilist_id deve ser maior que zero")
            anilist_id = raw_id
        else:
            anilist_id = None
        metadata_config = SeriesMetadataConfig(anilist_id=anilist_id)
    try:
        return SeriesConfig(
            source_language=src_lang,
            target_language=tgt_lang,
            track=subtitles.get("track"),
            styles=styles,
            metadata=metadata_config,
        )
    except ValidationError as exc:
        raise SeriesConfigError(f"{path}: {exc.errors()[0]['msg']}") from exc
