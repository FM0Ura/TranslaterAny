# tests/test_stage_orthography.py
"""Testes da etapa orthography."""

import httpx
from translaterany.stages.orthography import OrthographyStage


def test_orthography_stage_attributes() -> None:
    stage = OrthographyStage()
    assert stage.name == "orthography"
    assert stage.produces_dialogue is True
    assert stage.default_dialogue_input == "adapt"


def test_orthography_stage_graceful_degradation_when_offline() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    stage = OrthographyStage()
    stage.client = stage.make_client(transport=httpx.MockTransport(handler))

    outcome_texts, offline, applied = stage.process_texts({"u1": "Texto normal"}, exemptions=set())
    assert outcome_texts["u1"] == "Texto normal"
    assert offline is True
    assert applied == 0


def test_orthography_stage_applies_valid_edits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Erro de digitação",
                        "offset": 0,
                        "length": 4,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Você"}],
                    }
                ]
            },
        )

    stage = OrthographyStage()
    stage.client = stage.make_client(transport=httpx.MockTransport(handler))

    outcome_texts, offline, applied = stage.process_texts({"u1": "Voce foi lá?"}, exemptions=set())
    assert outcome_texts["u1"] == "Você foi lá?"
    assert offline is False
    assert applied == 1
