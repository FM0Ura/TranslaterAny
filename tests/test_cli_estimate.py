from pathlib import Path

from typer.testing import CliRunner

from translaterany.cli.app import app

runner = CliRunner()


def test_estimate_command_dry_run():
    result = runner.invoke(app, ["estimate", "--help"])
    assert result.exit_code == 0
    assert "estatísticas e estimativa de tokens" in result.output.lower()


def test_estimate_command_on_series(tmp_path: Path):
    series_dir = tmp_path / "Anime" / "Minha Serie"
    season = series_dir / "Season 1"
    season.mkdir(parents=True)
    (season / "S01E01.mkv").write_text("dummy")

    result = runner.invoke(app, ["estimate", str(series_dir)])
    assert result.exit_code == 0
    assert "Minha Serie" in result.output or "S01E01" in result.output or "estimativa" in result.output.lower()
    assert "token" in result.output.lower()
    assert "tempo" in result.output.lower()


def test_estimate_command_with_artifacts(tmp_path: Path):
    from translaterany.library import scan_library
    from translaterany.pipeline.artifacts import ArtifactStore
    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit

    series_dir = tmp_path / "Anime" / "Serie Real"
    season = series_dir / "Season 1"
    season.mkdir(parents=True)
    (season / "S01E01.mkv").write_text("dummy")

    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f'[general]\ndata_dir = "{data_dir}"\n[pipeline]\nstages = ["inventory", "select_track"]\n',
        encoding="utf-8",
    )

    scans = scan_library(series_dir, min_file_age=0)
    assert len(scans) == 1
    scan = scans[0]
    ep = scan.episodes[0]

    store = ArtifactStore(data_dir)
    art_dir = store.artifact_dir(scan.series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)

    norm_doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=["Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"],
        events=[],
        units=[
            Unit(id="u1", style="Default", text="Hello there, general Kenobi!", markers=0, events=[0]),
            Unit(id="u2", style="Default", text="You are a bold one.", markers=0, events=[1]),
            Unit(id="u3", style="Sign", text="Title Card", markers=0, events=[2]),
        ],
    )
    (art_dir / "normalize.json").write_text(norm_doc.model_dump_json(indent=2), encoding="utf-8")

    classification = Classification(
        main_style="Default",
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule="style"),
            "u2": UnitClass(type="dialogue", uncertain=False, rule="style"),
            "u3": UnitClass(type="sign", uncertain=False, rule="style"),
        },
        counts={"dialogue": 2, "sign": 1},
        scenes=[],
    )
    (art_dir / "classify.json").write_text(classification.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "estimate", str(series_dir)])
    assert result.exit_code == 0, result.output
    # 2 falas reais (não o fallback de 350)
    assert " 2 " in result.output or "2" in result.output
    assert "350" not in result.output
    assert "Serie" in result.output and "Real" in result.output
    assert "tempo" in result.output.lower()


def test_estimate_non_local_model_with_prices(tmp_path: Path):
    """Test that non-local models with prices show calculated cost, not 'local'."""
    from translaterany.library import scan_library
    from translaterany.pipeline.artifacts import ArtifactStore
    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit

    series_dir = tmp_path / "Anime" / "Priced Series"
    season = series_dir / "Season 1"
    season.mkdir(parents=True)
    (season / "S01E01.mkv").write_text("dummy")

    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f"""[general]
data_dir = "{data_dir}"
[pipeline]
stages = ["inventory", "select_track"]
[llm]
profile = "nuvem"
[llm.models.gpt-4o]
provider = "openai"
model = "gpt-4o"
input_price_per_mtok = 5.0
output_price_per_mtok = 15.0
[llm.profiles.nuvem]
translate = "gpt-4o"
review = "gpt-4o"
""",
        encoding="utf-8",
    )

    scans = scan_library(series_dir, min_file_age=0)
    assert len(scans) == 1
    scan = scans[0]
    ep = scan.episodes[0]

    store = ArtifactStore(data_dir)
    art_dir = store.artifact_dir(scan.series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)

    norm_doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=["Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"],
        events=[],
        units=[
            Unit(id="u1", style="Default", text="Hello world test", markers=0, events=[0]),
        ],
    )
    (art_dir / "normalize.json").write_text(norm_doc.model_dump_json(indent=2), encoding="utf-8")

    classification = Classification(
        main_style="Default",
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule="style"),
        },
        counts={"dialogue": 1},
        scenes=[],
    )
    (art_dir / "classify.json").write_text(classification.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "estimate", str(series_dir)])
    assert result.exit_code == 0, result.output
    # Should show cost, not "100% local"
    assert "100% local" not in result.output.lower()
    assert "custo" in result.output.lower()
    assert "usd" in result.output.lower()


def test_estimate_non_local_model_without_prices(tmp_path: Path):
    """Test that non-local models without prices show warning, not 'local'."""
    from translaterany.library import scan_library
    from translaterany.pipeline.artifacts import ArtifactStore
    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit

    series_dir = tmp_path / "Anime" / "Unpriced Series"
    season = series_dir / "Season 1"
    season.mkdir(parents=True)
    (season / "S01E01.mkv").write_text("dummy")

    data_dir = tmp_path / "data"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f"""[general]
data_dir = "{data_dir}"
[pipeline]
stages = ["inventory", "select_track"]
[llm]
profile = "nuvem"
[llm.models.gpt-4o]
provider = "openai"
model = "gpt-4o"
[llm.profiles.nuvem]
translate = "gpt-4o"
review = "gpt-4o"
""",
        encoding="utf-8",
    )

    scans = scan_library(series_dir, min_file_age=0)
    assert len(scans) == 1
    scan = scans[0]
    ep = scan.episodes[0]

    store = ArtifactStore(data_dir)
    art_dir = store.artifact_dir(scan.series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)

    norm_doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=["Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"],
        events=[],
        units=[
            Unit(id="u1", style="Default", text="Hello world test", markers=0, events=[0]),
        ],
    )
    (art_dir / "normalize.json").write_text(norm_doc.model_dump_json(indent=2), encoding="utf-8")

    classification = Classification(
        main_style="Default",
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule="style"),
        },
        counts={"dialogue": 1},
        scenes=[],
    )
    (art_dir / "classify.json").write_text(classification.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "estimate", str(series_dir)])
    assert result.exit_code == 0, result.output
    # Should show warning about missing prices, not "100% local"
    assert "100% local" not in result.output.lower()
    assert "preços não configurados" in result.output.lower() or "aviso" in result.output.lower()
    assert "0.00" in result.output
