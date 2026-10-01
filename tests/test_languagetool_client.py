# tests/test_languagetool_client.py
"""Testes do cliente LanguageTool."""

import httpx
from translaterany.orthography.client import LanguageToolClient


def test_languagetool_applies_typo_and_ignores_exemptions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Possível erro de digitação",
                        "offset": 0,
                        "length": 4,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Você"}],
                    },
                    {
                        "message": "Palavra desconhecida",
                        "offset": 9,
                        "length": 5,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Outra"}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = LanguageToolClient(url="http://localhost:8010/v2/check", timeout_s=5.0, transport=transport)

    # 'Shana' é nome isento
    text = "Voce e a Shana?"
    corrected, applied = client.correct_text(text, exemptions={"shana"})
    assert "Você" in corrected
    assert "Shana" in corrected  # não alterada
    assert applied == 1


def test_languagetool_ignores_colloquialisms_and_style() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Expressão coloquial",
                        "offset": 0,
                        "length": 3,
                        "rule": {"category": {"id": "COLLOQUIALISMS"}},
                        "replacements": [{"value": "Para"}],
                    },
                    {
                        "message": "Estilo",
                        "offset": 4,
                        "length": 2,
                        "rule": {"category": {"id": "STYLE"}},
                        "replacements": [{"value": "está"}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = LanguageToolClient(url="http://localhost:8010/v2/check", timeout_s=5.0, transport=transport)

    text = "Pra tá bom."
    corrected, applied = client.correct_text(text, exemptions=set())
    assert corrected == "Pra tá bom."
    assert applied == 0


def test_languagetool_graceful_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    client = LanguageToolClient(url="http://localhost:8010/v2/check", timeout_s=5.0, transport=transport)

    text = "Qualquer texto."
    corrected, applied = client.correct_text(text, exemptions=set())
    assert corrected == "Qualquer texto."
    assert applied == 0
    assert client.is_offline is True
