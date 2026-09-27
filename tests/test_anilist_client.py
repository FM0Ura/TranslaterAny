from pathlib import Path

import httpx

from translaterany.memory.anilist import AniListClient
from translaterany.memory.models import CharacterRole, EntrySource, Gender


def test_anilist_search_anime_success(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    mock_payload = {
        "data": {
            "Media": {
                "id": 20954,
                "idMal": 28999,
                "title": {"romaji": "Charlotte", "english": "Charlotte", "native": "シャーロット"},
                "seasonYear": 2015,
                "episodes": 13,
                "genres": ["Drama", "Supernatural"],
                "characters": {
                    "edges": [
                        {
                            "role": "MAIN",
                            "node": {
                                "name": {"full": "Yuu Otosaka", "native": "乙坂 有宇"},
                                "gender": "Male",
                            },
                        }
                    ]
                },
            }
        }
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, json=mock_payload))
    res = client.search_anime("Charlotte", 2015)
    assert res is not None
    assert res.anilist_id == 20954
    assert res.mal_id == 28999
    assert len(res.characters) == 1
    assert res.characters[0].name == "Yuu Otosaka"
    assert res.characters[0].native_name == "乙坂 有宇"
    assert res.characters[0].role == CharacterRole.MAIN
    assert res.characters[0].gender == Gender.MALE
    assert res.characters[0].source == EntrySource.METADATA
    assert (tmp_path / "cache" / "anilist").exists()


def test_anilist_search_cache_hit(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    call_count = 0

    def mock_post(*a, **kw):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 20954,
                        "idMal": 28999,
                        "title": {"romaji": "Charlotte", "english": "Charlotte"},
                        "seasonYear": 2015,
                        "genres": ["Drama"],
                        "characters": {"edges": []},
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)

    # First call - network
    res1 = client.search_anime("Charlotte", 2015)
    assert res1 is not None
    assert call_count == 1

    # Second call - should load from disk cache without calling network
    res2 = client.search_anime("Charlotte", 2015)
    assert res2 is not None
    assert res2.anilist_id == 20954
    assert call_count == 1


def test_anilist_offline_returns_none(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    def mock_post(*a, **kw):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.search_anime("Charlotte", 2015)
    assert res is None


def test_anilist_retry_on_429(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    attempts = 0

    def mock_post(*a, **kw):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(429, request=httpx.Request("POST", "https://graphql.anilist.co"))
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 1,
                        "idMal": 1,
                        "title": {"romaji": "Cowboy Bebop", "english": "Cowboy Bebop"},
                        "seasonYear": 1998,
                        "genres": ["Action", "Sci-Fi"],
                        "characters": {"edges": []},
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.search_anime("Cowboy Bebop", 1998)
    assert res is not None
    assert attempts == 2
    assert res.anilist_id == 1


def test_anilist_custom_client(tmp_path: Path):
    mock_payload = {
        "data": {
            "Media": {
                "id": 100,
                "idMal": 200,
                "title": {"romaji": "Custom Client Anime"},
                "seasonYear": 2024,
                "genres": [],
                "characters": {"edges": []},
            }
        }
    }

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload))
    custom_http_client = httpx.Client(transport=transport)

    client = AniListClient(cache_dir=tmp_path / "cache", client=custom_http_client)
    res = client.search_anime("Custom Client Anime")
    assert res is not None
    assert res.anilist_id == 100
    assert res.title == "Custom Client Anime"


def test_anilist_fallback_to_start_date_year(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    captured_payload = {}

    def mock_post(url, **kw):
        nonlocal captured_payload
        captured_payload = kw.get("json", {})
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 500,
                        "idMal": 600,
                        "title": {"romaji": "K-On! Movie"},
                        "seasonYear": None,
                        "startDate": {"year": 2011},
                        "genres": ["Music", "Comedy"],
                        "characters": {"edges": []},
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.search_anime("K-On! Movie")
    assert res is not None
    assert res.year == 2011
    query_str = captured_payload.get("query", "")
    assert "startDate" in query_str
    assert "year" in query_str


def test_anilist_search_with_year_query_includes_start_date(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")
    captured_payload = {}

    def mock_post(url, **kw):
        nonlocal captured_payload
        captured_payload = kw.get("json", {})
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 501,
                        "idMal": 601,
                        "title": {"romaji": "K-On! Movie"},
                        "seasonYear": 2011,
                        "startDate": {"year": 2011},
                        "genres": ["Music"],
                        "characters": {"edges": []},
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.search_anime("K-On! Movie", 2011)
    assert res is not None
    query_str = captured_payload.get("query", "")
    assert "startDate" in query_str


def test_anilist_get_anime_by_id_success(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")
    captured_payload = {}

    def mock_post(url, **kw):
        nonlocal captured_payload
        captured_payload = kw.get("json", {})
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 20954,
                        "idMal": 28999,
                        "title": {"romaji": "Charlotte", "english": "Charlotte"},
                        "seasonYear": 2015,
                        "genres": ["Drama"],
                        "characters": {
                            "edges": [
                                {
                                    "role": "MAIN",
                                    "node": {"name": {"full": "Yuu Otosaka"}, "gender": "Male"},
                                }
                            ]
                        },
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.get_anime_by_id(20954)
    assert res is not None
    assert res.anilist_id == 20954
    assert res.mal_id == 28999
    assert res.title == "Charlotte"
    assert len(res.characters) == 1
    assert captured_payload["variables"] == {"id": 20954}
    assert (tmp_path / "cache" / "anilist" / "id_20954.json").exists()


def test_anilist_get_anime_by_id_cache_hit(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")
    call_count = 0

    def mock_post(*a, **kw):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 20954,
                        "idMal": 28999,
                        "title": {"romaji": "Charlotte"},
                        "genres": [],
                        "characters": {"edges": []},
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    res1 = client.get_anime_by_id(20954)
    assert res1 is not None
    assert call_count == 1

    res2 = client.get_anime_by_id(20954)
    assert res2 is not None
    assert res2.anilist_id == 20954
    assert call_count == 1


def test_anilist_get_anime_by_id_offline(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    def mock_post(*a, **kw):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.get_anime_by_id(20954)
    assert res is None


def test_anilist_parse_invalid_id_mal(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    def mock_post(*a, **kw):
        return httpx.Response(
            200,
            json={
                "data": {
                    "Media": {
                        "id": 12345,
                        "idMal": "not-an-int",
                        "title": {"romaji": "Invalid Mal ID Anime"},
                        "genres": [],
                        "characters": {"edges": []},
                    }
                }
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    match = client.get_anime_by_id(12345)
    assert match is not None
    assert match.anilist_id == 12345
    assert match.mal_id is None
