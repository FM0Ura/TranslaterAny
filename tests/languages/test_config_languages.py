# tests/languages/test_config_languages.py
from pathlib import Path
import pytest
from translaterany.config import load_config_from_str
from translaterany.config.model import AppConfig, ConfigError
from translaterany.library.series_config import load_series_config
from translaterany.languages.registry import LanguageRegistry
from translaterany.pipeline.runner import PipelineRunner


def test_default_languages_in_config() -> None:
    cfg = load_config_from_str("")
    assert cfg.source_language == "en"
    assert cfg.target_language == "pt-BR"


def test_custom_languages_in_config() -> None:
    raw = """
    source_language = "ja"
    target_language = "es"
    """
    cfg = load_config_from_str(raw)
    assert cfg.source_language == "ja"
    assert cfg.target_language == "es"


def test_same_languages_raises_config_error() -> None:
    raw = """
    source_language = "pt-BR"
    target_language = "pt-BR"
    """
    with pytest.raises(ValueError, match="não podem ser iguais"):
        load_config_from_str(raw)


def test_series_config_languages(tmp_path: Path) -> None:
    series_toml = tmp_path / "series.toml"
    series_toml.write_text(
        """
        source_language = "ja"
        target_language = "es"
        """,
        encoding="utf-8",
    )
    s_cfg = load_series_config(tmp_path)
    assert s_cfg.source_language == "ja"
    assert s_cfg.target_language == "es"


def test_pipeline_runner_precedence() -> None:
    # 1. Config base
    app_cfg = load_config_from_str(
        """
        source_language = "en"
        target_language = "pt-BR"
        """
    )
    # Runner herda do app_cfg
    pr = PipelineRunner(app_cfg)
    assert pr.source_language.code == "en"
    assert pr.target_language.code == "pt-BR"

    # 2. CLI sobrepõe app_cfg
    pr_cli = PipelineRunner(app_cfg, source_language="ja", target_language="es")
    assert pr_cli.source_language.code == "ja"
    assert pr_cli.target_language.code == "es"
