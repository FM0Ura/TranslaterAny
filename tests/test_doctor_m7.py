# tests/test_doctor_m7.py
"""Testes do doctor com checagem de LanguageTool."""

import httpx
from translaterany.cli.doctor import check_languagetool_service


def test_doctor_languagetool_check_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"name": "Portuguese (Brazil)"}])

    transport = httpx.MockTransport(handler)
    res = check_languagetool_service("http://localhost:8010/v2/check", transport=transport)
    assert res.status == "ok"
    assert "acessível" in res.message


def test_doctor_languagetool_check_warn_when_offline() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    res = check_languagetool_service("http://localhost:8010/v2/check", transport=transport)
    assert res.status == "warn"
    assert "indisponível" in res.message
