"""Testes de carregamento de arquivo .env."""

from pathlib import Path

from translaterany.config.dotenv import load_dotenv
from translaterany.config.loader import load_config


def test_load_dotenv_reads_key_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # Comentário
        TEST_VAR_A=123
        TEST_VAR_B="hello world"
        TEST_VAR_C='single quotes'
        """,
        encoding="utf-8",
    )

    monkeypatch.delenv("TEST_VAR_A", raising=False)
    monkeypatch.delenv("TEST_VAR_B", raising=False)
    monkeypatch.delenv("TEST_VAR_C", raising=False)

    assert load_dotenv(env_file) is True

    import os
    assert os.environ.get("TEST_VAR_A") == "123"
    assert os.environ.get("TEST_VAR_B") == "hello world"
    assert os.environ.get("TEST_VAR_C") == "single quotes"


def test_load_dotenv_does_not_override_existing(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ALREADY_SET=new_value\n", encoding="utf-8")

    monkeypatch.setenv("ALREADY_SET", "initial_value")

    assert load_dotenv(env_file) is True

    import os
    assert os.environ.get("ALREADY_SET") == "initial_value"


def test_load_config_with_cloud_model_env(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATERANY_LLM_PROFILE", "nuvem")
    monkeypatch.setenv("TRANSLATERANY_CLOUD_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-gemini")

    cfg = load_config()
    assert cfg.llm.profile == "nuvem"
    assert "gemini-2.5-flash" in cfg.llm.models
    assert cfg.llm.models["gemini-2.5-flash"].provider == "gemini"
    assert cfg.llm.profiles["nuvem"].translate == "gemini-2.5-flash"
    assert cfg.llm.profiles["nuvem"].review == "gemini-2.5-flash"


def test_load_config_multi_model_flow(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATERANY_LLM_PROFILE", "nuvem")
    monkeypatch.setenv("TRANSLATERANY_MODEL_TRANSLATE", "gemini-2.5-flash")
    monkeypatch.setenv("TRANSLATERANY_MODEL_REVIEW", "gpt-4o")
    monkeypatch.setenv("TRANSLATERANY_STAGE_FINAL_READTHROUGH_MODEL", "gpt-4o")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    cfg = load_config()
    assert cfg.llm.profile == "nuvem"
    assert cfg.llm.profiles["nuvem"].translate == "gemini-2.5-flash"
    assert cfg.llm.profiles["nuvem"].review == "gpt-4o"
    assert cfg.llm.models["gemini-2.5-flash"].provider == "gemini"
    assert cfg.llm.models["gpt-4o"].provider == "openai"

    final_stage = next(s for s in cfg.stages if s.name == "final_readthrough")
    assert getattr(final_stage.options, "model") == "gpt-4o"


def test_load_config_thinking_flag(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATERANY_LLM_PROFILE", "nuvem")
    monkeypatch.setenv("TRANSLATERANY_MODEL_REVIEW", "gemini-3.5-flash")
    monkeypatch.setenv("TRANSLATERANY_LLM_THINK", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    cfg_false = load_config()
    assert cfg_false.llm.models["gemini-3.5-flash"].think is False

    monkeypatch.setenv("TRANSLATERANY_LLM_THINK", "true")
    cfg_true = load_config()
    assert cfg_true.llm.models["gemini-3.5-flash"].think is True



