from unittest.mock import patch

from typer.testing import CliRunner

from translaterany.cli import app

runner = CliRunner()


def test_cli_web_help() -> None:
    result = runner.invoke(app, ["web", "--help"])
    assert result.exit_code == 0
    assert "Inicia o servidor da interface Web" in result.stdout


def test_cli_web_run_mocked() -> None:
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(app, ["web", "--port", "9090", "--no-open-browser"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert kwargs["port"] == 9090
