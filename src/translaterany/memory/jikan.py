"""Cliente para a API REST do Jikan (MyAnimeList v4) com cache em disco e retry."""

import json
import logging
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from translaterany.memory.models import EpisodeSynopsis

logger = logging.getLogger(__name__)

JIKAN_API_BASE_URL = "https://api.jikan.moe/v4"


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Retorna True se o erro HTTP for passível de nova tentativa (429 ou 5xx)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


class JikanClient:
    """Cliente para a API REST do Jikan com cache em disco."""

    def __init__(self, cache_dir: Path, client: httpx.Client | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.jikan_dir = self.cache_dir / "jikan"
        self.jikan_dir.mkdir(parents=True, exist_ok=True)
        self._client = client

    @retry(
        retry=retry_if_exception(_is_retryable_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=0.5),
        reraise=True,
    )
    def _get_with_retry(self, url: str, **kwargs) -> httpx.Response:
        if self._client is not None:
            resp = self._client.get(url, **kwargs)
        else:
            resp = httpx.get(url, **kwargs)
        if resp.status_code in (429, 500, 502, 503, 504):
            resp.raise_for_status()
        return resp

    def clear_cache(self, mal_id: int) -> None:
        """Remove o arquivo de cache em disco para o mal_id especificado."""
        (self.jikan_dir / f"{mal_id}_episodes.json").unlink(missing_ok=True)

    def get_episode_synopses(self, mal_id: int) -> dict[int, EpisodeSynopsis]:
        """Obtém sinopses de episódios do Jikan por mal_id com fallback para cache em disco."""
        cache_file = self.jikan_dir / f"{mal_id}_episodes.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return {item["number"]: EpisodeSynopsis.model_validate(item) for item in data}
                if isinstance(data, dict):
                    return {int(k): EpisodeSynopsis.model_validate(v) for k, v in data.items()}
            except Exception as exc:
                logger.warning("Falha ao ler cache do Jikan em %s: %s", cache_file, exc)

        url = f"{JIKAN_API_BASE_URL}/anime/{mal_id}/episodes"
        episodes: dict[int, EpisodeSynopsis] = {}
        page = 1

        while True:
            try:
                resp = self._get_with_retry(url, params={"page": page})
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("Falha de rede/HTTP ao consultar Jikan para mal_id=%s (pág %s): %s", mal_id, page, exc)
                return episodes if episodes else {}

            if resp.status_code != 200:
                logger.warning("Jikan retornou status code %s para mal_id=%s", resp.status_code, mal_id)
                return episodes if episodes else {}

            try:
                payload = resp.json()
            except Exception as exc:
                logger.warning("Falha ao decodificar JSON do Jikan para mal_id=%s: %s", mal_id, exc)
                return episodes if episodes else {}

            items = payload.get("data") or []
            for item in items:
                if not isinstance(item, dict) or "mal_id" not in item:
                    continue
                ep_num = int(item["mal_id"])
                episodes[ep_num] = EpisodeSynopsis(
                    episode_key=f"EP{ep_num}",
                    number=ep_num,
                    title=item.get("title"),
                    synopsis=item.get("synopsis") or "",
                )

            pagination = payload.get("pagination") or {}
            has_next = pagination.get("has_next_page", False)
            if not has_next:
                break
            page += 1

        if episodes:
            try:
                serialized = [ep.model_dump(mode="json") for ep in episodes.values()]
                cache_file.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.warning("Falha ao salvar cache do Jikan em %s: %s", cache_file, exc)

        return episodes
