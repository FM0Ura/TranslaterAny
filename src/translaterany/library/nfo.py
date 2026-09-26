"""Identidade estável da série a partir do tvshow.nfo (Jellyfin/Kodi/Sonarr)."""

import xml.etree.ElementTree as ET
from pathlib import Path

_ID_TAGS = (("tvdb", "tvdbid"), ("tmdb", "tmdbid"), ("imdb", "imdb_id"))


def series_identity(root: Path) -> str | None:
    """`tvdb:<id>` (ou tmdb/imdb) do tvshow.nfo; None se ausente ou ilegível."""
    nfo = root / "tvshow.nfo"
    if not nfo.is_file():
        return None
    try:
        tree = ET.parse(nfo)
    except ET.ParseError, OSError:
        return None
    for prefix, tag in _ID_TAGS:
        element = tree.getroot().find(tag)
        if element is not None and element.text and element.text.strip():
            return f"{prefix}:{element.text.strip()}"
    return None
