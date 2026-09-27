"""Teste ponta a ponta (E2E) do Marco 4: Tradução Contextual."""

from pathlib import Path

import pytest
from mkvtools import Sub, make_mkv, needs_mkvtoolnix

from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.subtitles.ass import parse_ass

pytestmark = needs_mkvtoolnix

ASS_CONTENT = """[Script Info]
Title: Test Anime
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,10,1
Style: Sign,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,8,10,10,10,1
Style: Song_EN,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,8,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:00.00,0:01:30.00,Song_EN,,0,0,0,,Brave shine in the night
Dialogue: 0,0:02:00.00,0:02:05.00,Sign,,0,0,0,,Student Council
Dialogue: 0,0:03:00.00,0:03:02.00,Default,,0,0,0,,Wait for me...
Dialogue: 0,0:03:02.20,0:03:04.00,Default,,0,0,0,,...I am coming!
"""


def test_m4_e2e_pipeline_two_episodes(tmp_path: Path):
    series_dir = tmp_path / "library" / "Test Anime (2025)"
    season_dir = series_dir / "Season 1"
    season_dir.mkdir(parents=True)

    ep1_mkv = season_dir / "Test Anime - S01E01.mkv"
    ep2_mkv = season_dir / "Test Anime - S01E02.mkv"

    make_mkv(ep1_mkv, [Sub(ASS_CONTENT, "Full Dialogue", default=True)])
    make_mkv(ep2_mkv, [Sub(ASS_CONTENT, "Full Dialogue", default=True)])

    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)

    fake_llm = FakeLLM(
        responses={
            "Brave shine in the night": "Brilho corajoso na noite",
            "Student Council": "Conselho Estudantil",
            "Wait for me... ...I am coming!": "Espere por mim... já estou chegando!",
        }
    )

    # Constrói instâncias do DEFAULT_PIPELINE
    stages_instances = []
    for name in DEFAULT_PIPELINE:
        if name == "remux":
            continue
        if name == "metadata":
            stages_instances.append(MetadataStage(anilist_client=None, jikan_client=None))
        else:
            stages_instances.append(REGISTRY.get(name)())

    series, episodes = discover(series_dir)
    assert len(episodes) == 2

    runner = Runner(stages=stages_instances, store=store, llm=fake_llm)
    summary1 = runner.run(series, [episodes[0]])
    assert not summary1.failed
    assert summary1.status == "success"

    summary2 = runner.run(series, [episodes[1]])
    assert not summary2.failed
    assert summary2.status == "success"

    # Verifica arquivo ASS publicado do Ep 1
    pub1 = season_dir / "Test Anime - S01E01.pt-BR.ass"
    assert pub1.exists()
    ep1_ass = parse_ass(pub1.read_bytes())
    ep1_texts = [ev.text for ev in ep1_ass.events]
    assert any("Brilho corajoso na noite" in t for t in ep1_texts)
    assert any("Conselho Estudantil" in t for t in ep1_texts)
    assert any("Espere por mim" in t for t in ep1_texts)

    # Verifica arquivo ASS publicado do Ep 2
    pub2 = season_dir / "Test Anime - S01E02.pt-BR.ass"
    assert pub2.exists()
    ep2_ass = parse_ass(pub2.read_bytes())
    ep2_texts = [ev.text for ev in ep2_ass.events]
    assert any("Brilho corajoso na noite" in t for t in ep2_texts)
    assert any("Conselho Estudantil" in t for t in ep2_texts)

    # Verifica que a memória de tradução foi alimentada e salvou as entradas
    tm_file = store.series_dir(series.key) / "memory" / "translation_memory.yaml"
    assert tm_file.exists()
    content = tm_file.read_text(encoding="utf-8")
    assert "brave shine in the night" in content.lower()
    assert "student council" in content.lower()

    from translaterany.subtitles.translator import TranslationBatch

    # Verifica que chamadas de tradução para músicas ocorreram apenas 1 vez (no Ep 1) e NUNCA no Ep 2 (reuso da TM)
    song_calls = [
        call for call in fake_llm.calls
        if call.output_type is TranslationBatch and "Brave shine in the night" in call.prompt
    ]
    assert len(song_calls) == 1, f"Esperada exatamente 1 chamada de música, obtido {len(song_calls)}"

    # Verifica que chamadas de tradução para placas ocorreram apenas 1 vez (no Ep 1) e NUNCA no Ep 2 (reuso da TM)
    sign_calls = [
        call for call in fake_llm.calls
        if call.output_type is TranslationBatch and "Student Council" in call.prompt
    ]
    assert len(sign_calls) == 1, f"Esperada exatamente 1 chamada de placa, obtido {len(sign_calls)}"
