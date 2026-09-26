from pathlib import Path

import httpx

from translaterany.memory.jikan import JikanClient


def test_jikan_get_episode_synopses_success(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")
    mock_payload = {
        "data": [
            {
                "mal_id": 1,
                "title": "I Think About Others",
                "synopsis": "Yuu Otosaka uses his ability to cheat on tests.",
            }
        ]
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json=mock_payload))
    eps = client.get_episode_synopses(28999)
    assert 1 in eps
    assert "cheat" in eps[1].synopsis
    assert eps[1].title == "I Think About Others"
    assert eps[1].number == 1
    assert eps[1].episode_key == "EP1"
    assert (tmp_path / "cache" / "jikan" / "28999_episodes.json").exists()


def test_jikan_get_episode_synopses_cache_hit(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")

    call_count = 0

    def mock_get(*a, **kw):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "mal_id": 1,
                        "title": "Episode 1",
                        "synopsis": "First synopsis",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", mock_get)

    # First call: hits network and populates cache
    eps1 = client.get_episode_synopses(12345)
    assert 1 in eps1
    assert call_count == 1

    # Second call: reads from cache file
    eps2 = client.get_episode_synopses(12345)
    assert 1 in eps2
    assert eps2[1].synopsis == "First synopsis"
    assert call_count == 1


def test_jikan_offline_returns_empty_dict(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")

    def mock_get(*a, **kw):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "get", mock_get)
    eps = client.get_episode_synopses(28999)
    assert eps == {}


def test_jikan_retry_on_429(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")

    attempts = 0

    def mock_get(*a, **kw):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(429, request=httpx.Request("GET", "https://api.jikan.moe/v4/anime/1/episodes"))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "mal_id": 1,
                        "title": "Asteroid Blues",
                        "synopsis": "Spike Spiegel and Jet Black pursue a bounty.",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    eps = client.get_episode_synopses(1)
    assert 1 in eps
    assert attempts == 2
    assert eps[1].title == "Asteroid Blues"


def test_jikan_null_synopsis_handled(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")

    mock_payload = {
        "data": [
            {
                "mal_id": 2,
                "title": "Episode Without Synopsis",
                "synopsis": None,
            }
        ]
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json=mock_payload))
    eps = client.get_episode_synopses(99999)
    assert 2 in eps
    assert eps[2].synopsis == ""
    assert eps[2].title == "Episode Without Synopsis"


def test_jikan_custom_client(tmp_path: Path):
    mock_payload = {
        "data": [
            {
                "mal_id": 5,
                "title": "Custom Client Episode",
                "synopsis": "Works via injected client",
            }
        ]
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload))
    custom_http_client = httpx.Client(transport=transport)

    client = JikanClient(cache_dir=tmp_path / "cache", client=custom_http_client)
    eps = client.get_episode_synopses(555)
    assert 5 in eps
    assert eps[5].title == "Custom Client Episode"
