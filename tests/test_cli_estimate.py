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
