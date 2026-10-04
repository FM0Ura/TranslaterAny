# tests/stages/test_publish_remux_multilingual.py
from pathlib import Path
from types import SimpleNamespace

import httpx

from translaterany.languages.registry import LanguageRegistry
from translaterany.media.remux import build_remux_command
from translaterany.stages.orthography import OrthographyStage
from translaterany.stages.publish import get_output_ass_path
from translaterany.subtitles.texts import UnitTexts
from translaterany.util.doctor import check_languagetool_service


def test_publish_output_path_uses_target_language() -> None:
    mkv_path = Path("/media/anime/Charlotte S01E01.mkv")
    es = LanguageRegistry.resolve("es")
    out_es = get_output_ass_path(mkv_path, target_lang=es)
    assert out_es.name == "Charlotte S01E01.es.ass"

    pt = LanguageRegistry.resolve("pt-BR")
    out_pt = get_output_ass_path(mkv_path, target_lang=pt)
    assert out_pt.name == "Charlotte S01E01.pt-BR.ass"


def test_remux_command_uses_target_language() -> None:
    es = LanguageRegistry.resolve("es")
    cmd = build_remux_command(Path("video.mkv"), Path("video.es.ass"), target_lang=es)
    cmd_str = " ".join(cmd)
    assert "--language 0:es" in cmd_str or "--language 0:spa" in cmd_str
    assert "Espanhol — TranslaterAny" in cmd_str


def test_remux_command_uses_pt_br_by_default() -> None:
    cmd = build_remux_command(Path("video.mkv"), Path("video.pt-BR.ass"))
    cmd_str = " ".join(cmd)
    assert "--language 0:pt-BR" in cmd_str
    assert "Português (Brasil) — TranslaterAny" in cmd_str


def test_orthography_stage_updates_client_language() -> None:
    stage = OrthographyStage()
    assert stage.client.language == "pt-BR"

    mock_inputs = SimpleNamespace(json=lambda name, model: UnitTexts(texts={"1": "Texto"}) if name == "adapt" else None)
    mock_output = SimpleNamespace(json=lambda data: None)
    ctx = SimpleNamespace(
        inputs=mock_inputs,
        output=mock_output,
        target_language=LanguageRegistry.resolve("es"),
        series=SimpleNamespace(key="s1"),
        episode=SimpleNamespace(key="e1"),
        log=SimpleNamespace(warning=lambda *a, **kw: None),
        stats={},
    )
    stage.run(ctx)
    assert stage.client.language == "es"


def test_doctor_languagetool_supports_target_lang() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"code": "es", "name": "Spanish"}])

    transport = httpx.MockTransport(handler)
    res = check_languagetool_service("http://localhost:8010/v2/check", transport=transport, target_lang="es")
    assert res.status == "ok"
    assert "suporta es" in res.message
