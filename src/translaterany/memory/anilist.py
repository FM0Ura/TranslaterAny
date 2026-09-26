"""Cliente para a API GraphQL do AniList com cache em disco e retry."""

import hashlib
import json
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from translaterany.memory.models import CharacterEntry, CharacterRole, EntrySource, Gender

logger = logging.getLogger(__name__)

ANILIST_API_URL = "https://graphql.anilist.co"

ANILIST_SEARCH_QUERY = """
query ($search: String) {
  Media (search: $search, type: ANIME, sort: SEARCH_MATCH) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    seasonYear
    startDate {
      year
    }
    episodes
    genres
    characters (sort: [ROLE, RELEVANCE]) {
      edges {
        role
        node {
          name {
            full
            native
          }
          gender
        }
      }
    }
  }
}
"""

ANILIST_SEARCH_WITH_YEAR_QUERY = """
query ($search: String, $year: Int) {
  Media (search: $search, seasonYear: $year, type: ANIME, sort: SEARCH_MATCH) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    seasonYear
    startDate {
      year
    }
    episodes
    genres
    characters (sort: [ROLE, RELEVANCE]) {
      edges {
        role
        node {
          name {
            full
            native
          }
          gender
        }
      }
    }
  }
}
"""

ANILIST_GET_BY_ID_QUERY = """
query ($id: Int) {
  Media (id: $id, type: ANIME) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    seasonYear
    startDate {
      year
    }
    episodes
    genres
    characters (sort: [ROLE, RELEVANCE]) {
      edges {
        role
        node {
          name {
            full
            native
          }
          gender
        }
      }
    }
  }
}
"""


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Retorna True se o erro HTTP for passível de nova tentativa (429 ou 5xx)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


class AniListMatch(BaseModel):
    anilist_id: int
    mal_id: int | None = None
    title: str
    romaji: str
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    characters: list[CharacterEntry] = Field(default_factory=list)


def _parse_media_to_match(media: dict, fallback_title: str) -> AniListMatch:
    title_dict = media.get("title") or {}
    romaji = title_dict.get("romaji") or ""
    anime_title = title_dict.get("english") or romaji or title_dict.get("native") or fallback_title

    characters: list[CharacterEntry] = []
    edges = media.get("characters", {}).get("edges", []) or []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node") or {}
        name_dict = node.get("name") or {}
        full_name = name_dict.get("full") or name_dict.get("userPreferred") or ""
        if not full_name:
            continue
        native_name = name_dict.get("native")

        role_raw = str(edge.get("role") or "").strip().lower()
        if role_raw == "main":
            role = CharacterRole.MAIN
        elif role_raw == "supporting":
            role = CharacterRole.SUPPORTING
        elif role_raw == "background":
            role = CharacterRole.BACKGROUND
        else:
            role = CharacterRole.SUPPORTING

        gender_raw = str(node.get("gender") or "").strip().lower()
        if gender_raw in ("male", "man", "m"):
            gender = Gender.MALE
        elif gender_raw in ("female", "woman", "f"):
            gender = Gender.FEMALE
        elif gender_raw in ("neutral", "non-binary"):
            gender = Gender.NEUTRAL
        else:
            gender = Gender.UNKNOWN

        characters.append(
            CharacterEntry(
                name=full_name,
                native_name=native_name,
                role=role,
                gender=gender,
                source=EntrySource.METADATA,
            )
        )

    mal_id_raw = media.get("idMal")
    try:
        mal_id = int(mal_id_raw) if mal_id_raw is not None else None
    except ValueError, TypeError:
        mal_id = None

    start_date = media.get("startDate")
    start_year = start_date.get("year") if isinstance(start_date, dict) else None
    year_val = media.get("seasonYear") or start_year

    return AniListMatch(
        anilist_id=int(media["id"]),
        mal_id=mal_id,
        title=anime_title,
        romaji=romaji,
        year=year_val,
        genres=media.get("genres") or [],
        characters=characters,
    )


class AniListClient:
    """Cliente para a API GraphQL do AniList com cache em disco."""

    def __init__(self, cache_dir: Path, client: httpx.Client | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.anilist_dir = self.cache_dir / "anilist"
        self.anilist_dir.mkdir(parents=True, exist_ok=True)
        self._client = client

    @retry(
        retry=retry_if_exception(_is_retryable_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=0.5),
        reraise=True,
    )
    def _post_with_retry(self, url: str, **kwargs) -> httpx.Response:
        if self._client is not None:
            resp = self._client.post(url, **kwargs)
        else:
            resp = httpx.post(url, **kwargs)
        if resp.status_code in (429, 500, 502, 503, 504):
            resp.raise_for_status()
        return resp

    def _get_cache_path(self, title: str, year: int | None) -> Path:
        norm_key = f"{title.strip().lower()}::{year or ''}"
        cache_hash = hashlib.sha256(norm_key.encode("utf-8")).hexdigest()[:16]
        return self.anilist_dir / f"{cache_hash}.json"

    def search_anime(self, title: str, year: int | None = None) -> AniListMatch | None:
        """Busca metadados de anime no AniList com fallback para cache em disco."""
        cache_file = self._get_cache_path(title, year)
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return AniListMatch.model_validate(data)
            except Exception as exc:
                logger.warning("Falha ao ler cache do AniList em %s: %s", cache_file, exc)

        if year is not None:
            query = ANILIST_SEARCH_WITH_YEAR_QUERY
            variables: dict[str, str | int] = {"search": title, "year": year}
        else:
            query = ANILIST_SEARCH_QUERY
            variables = {"search": title}

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        payload = {"query": query, "variables": variables}

        try:
            resp = self._post_with_retry(ANILIST_API_URL, json=payload, headers=headers)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning("Falha de rede/HTTP ao consultar AniList para '%s': %s", title, exc)
            return None

        if resp.status_code != 200:
            logger.warning("AniList retornou status code %s para '%s'", resp.status_code, title)
            return None

        try:
            body = resp.json()
        except Exception as exc:
            logger.warning("Falha ao decodificar JSON do AniList para '%s': %s", title, exc)
            return None

        if not isinstance(body, dict):
            logger.warning("Resposta inválida do AniList (não-dicionário) para '%s'", title)
            return None

        data = body.get("data")
        if not isinstance(data, dict):
            return None

        media = data.get("Media")
        if not media or not isinstance(media, dict):
            return None

        match = _parse_media_to_match(media, fallback_title=title)

        try:
            cache_file.write_text(match.model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Falha ao salvar cache do AniList em %s: %s", cache_file, exc)

        return match

    def get_anime_by_id(self, anilist_id: int) -> AniListMatch | None:
        """Busca metadados de anime no AniList pelo ID com fallback para cache em disco."""
        cache_file = self.anilist_dir / f"id_{anilist_id}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return AniListMatch.model_validate(data)
            except Exception as exc:
                logger.warning("Falha ao ler cache do AniList em %s: %s", cache_file, exc)

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        payload = {"query": ANILIST_GET_BY_ID_QUERY, "variables": {"id": anilist_id}}

        try:
            resp = self._post_with_retry(ANILIST_API_URL, json=payload, headers=headers)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning("Falha de rede/HTTP ao consultar AniList para id=%s: %s", anilist_id, exc)
            return None

        if resp.status_code != 200:
            logger.warning("AniList retornou status code %s para id=%s", resp.status_code, anilist_id)
            return None

        try:
            body = resp.json()
        except Exception as exc:
            logger.warning("Falha ao decodificar JSON do AniList para id=%s: %s", anilist_id, exc)
            return None

        if not isinstance(body, dict):
            logger.warning("Resposta inválida do AniList (não-dicionário) para id=%s", anilist_id)
            return None

        data = body.get("data")
        if not isinstance(data, dict):
            return None

        media = data.get("Media")
        if not media or not isinstance(media, dict):
            return None

        match = _parse_media_to_match(media, fallback_title=f"AniList-{anilist_id}")

        try:
            cache_file.write_text(match.model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Falha ao salvar cache do AniList em %s: %s", cache_file, exc)

        return match
