"""Testes de integração ponta a ponta do Marco 3 (M3).

Valida a execução completa do pipeline de 11 etapas com memória da série:
inventory -> metadata -> select_track -> extract -> normalize -> classify ->
extract_terms -> consolidate_memory -> translate_dialogue -> write -> publish.
"""

from pathlib import Path

import httpx
from mkvtools import create_synthetic_mkv, needs_mkvtoolnix

from translaterany.config.loader import load_config_from_str
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.runner import PipelineRunner
from translaterany.stages.extract_terms import ExtractTermsResponse


@needs_mkvtoolnix
def test_m3_pipeline_end_to_end_with_memory(tmp_path: Path, monkeypatch) -> None:
    # 1. Mock de APIs externas
    mock_anilist = {
        "data": {
            "Media": {
                "id": 20954,
                "idMal": 28999,
                "title": {"romaji": "Charlotte", "english": "Charlotte", "native": "シャーロット"},
                "seasonYear": 2015,
                "episodes": 1,
                "genres": ["Supernatural"],
                "characters": {"edges": []},
            }
        }
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, json=mock_anilist))
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json={"data": []}))

    # 2. Criação do MKV sintético com termo especial
    series_dir = tmp_path / "Charlotte (2015)"
    video_path = series_dir / "Season 1" / "S01E01.mkv"
    create_synthetic_mkv(
        video_path,
        dialogues=[
            ("00:00:01.000", "00:00:03.000", "Welcome to Hoshinoumi Academy!"),
            ("00:00:04.000", "00:00:06.000", "He has the Plunder ability."),
        ],
    )

    # 3. FakeLLM respondendo à extração e à tradução com o termo do glossário
    fake_extract = ExtractTermsResponse(
        terms=[
            {"term": "Hoshinoumi Academy", "translation": "Academia Hoshinoumi", "category": "place"},
            {"term": "Plunder", "translation": "Saque", "category": "technique"},
        ]
    )
    fake_llm = FakeLLM(
        script=[fake_extract],
        responses={
            "Welcome to Hoshinoumi Academy!": "Bem-vindo à Academia Hoshinoumi!",
            "He has the Plunder ability.": "Ele tem a habilidade Saque.",
        },
    )

    data_dir = tmp_path / "data"
    config = load_config_from_str(f'[general]\ndata_dir = "{data_dir}"\n')
    runner = PipelineRunner(config=config, client=fake_llm, store=ArtifactStore(data_dir))
    summary = runner.run_series(series_dir)
    assert not summary.failed
    assert summary.status == "success"

    # 4. Verifica geração dos arquivos YAML de memória
    store = ArtifactStore(data_dir)
    series_key = "charlotte-2015"
    mem_dir = store.series_dir(series_key) / "memory"
    assert (mem_dir / "glossary.yaml").exists()
    assert (mem_dir / "story.yaml").exists()
    assert (mem_dir / "characters.yaml").exists()

    # 5. Verifica arquivo .pt-BR.ass gerado com a tradução padronizada
    ass_files = list(series_dir.glob("**/*.pt-BR.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text(encoding="utf-8")
    assert "; TranslaterAny" in content
    assert "Academia Hoshinoumi" in content
    assert "Saque" in content
