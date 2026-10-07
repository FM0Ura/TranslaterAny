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


def test_languagetool_ignores_honorifics_and_token_exemptions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Palavra desconhecida",
                        "offset": 15,
                        "length": 7,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Violou"}],
                    },
                    {
                        "message": "Palavra desconhecida",
                        "offset": 29,
                        "length": 3,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "cum"}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = LanguageToolClient(url="http://localhost:8010/v2/check", timeout_s=5.0, transport=transport)

    text = "Concordo com o Hyoudou Issei-kun!"
    # Exenções contendo tokens de nomes e honorífico
    corrected, applied = client.correct_text(text, exemptions={"hyoudou", "issei", "kun"})
    assert corrected == "Concordo com o Hyoudou Issei-kun!"
    assert applied == 0


def test_languagetool_ignores_capitalized_proper_nouns_mid_sentence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Palavra desconhecida",
                        "offset": 12,
                        "length": 6,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Karin"}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = LanguageToolClient(url="http://localhost:8010/v2/check", timeout_s=5.0, transport=transport)

    text = "Falando com Okarin sobre isso."
    # Mesmo sem 'okarin' explicitamente em exemptions, não deve substituir palavra com maiúscula no meio da frase
    corrected, applied = client.correct_text(text, exemptions=set())
    assert corrected == "Falando com Okarin sobre isso."
    assert applied == 0



def _client_with_match(text: str, target: str, category: str, replacement: str) -> LanguageToolClient:
    offset = text.index(target)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "x",
                        "offset": offset,
                        "length": len(target),
                        "rule": {"category": {"id": category}},
                        "replacements": [{"value": replacement}],
                    }
                ]
            },
        )

    return LanguageToolClient(url="http://localhost:8010/v2/check", transport=httpx.MockTransport(handler))


def test_languagetool_rejects_word_swaps_on_loanwords_and_onomatopoeia() -> None:
    """Regressão: 'tsundere'->'sugere', 'nyan'->'miam', 'Putz'->'Pubs' corrompiam falas."""
    cases = [
        ("Eu não sou tsundere nem yandere!", "tsundere", "sugere"),
        ("Desculpa a demora, Kyouma! Nyan~!", "Nyan", "Nyhan"),
        ("Putz, o quê?", "Putz", "Pubs"),
        ("Fica ótimo com essa roupa de miko...", "miko", "mico"),
        ("Mayushii! Tissuinha! Rápido!", "Tissuinha", "Diclinia"),
    ]
    for text, target, replacement in cases:
        client = _client_with_match(text, target, "TYPOS", replacement)
        corrected, applied = client.correct_text(text, exemptions=set())
        assert corrected == text, (text, corrected)
        assert applied == 0


def test_languagetool_rejects_grammar_and_casing_rewrites() -> None:
    """Regressão: 'uma gênio'->'um gênio', 'e-mails'->'e-Mails', 'você'->'Você' em fragmentos."""
    cases = [
        ("Aposto que você é uma gênio doida, né?", "uma", "GRAMMAR", "um"),
        ("Mandei os e-mails ontem.", "mails", "CASING", "Mails"),
        ("você não vai falhar...", "você", "CASING", "Você"),
    ]
    for text, target, category, replacement in cases:
        client = _client_with_match(text, target, category, replacement)
        corrected, applied = client.correct_text(text, exemptions=set())
        assert corrected == text, (text, corrected)
        assert applied == 0


def test_languagetool_still_applies_accent_only_fixes() -> None:
    text = "Incrívelmente bom."
    client = _client_with_match(text, "Incrívelmente", "TYPOS", "Incrivelmente")
    corrected, applied = client.correct_text(text, exemptions=set())
    assert corrected == "Incrivelmente bom."
    assert applied == 1

    text = "Voce sabe."
    client = _client_with_match(text, "Voce", "TYPOS", "Você")
    corrected, applied = client.correct_text(text, exemptions=set())
    assert corrected == "Você sabe."
    assert applied == 1

