"""Testes de configuração do Marco 8 (Portões e QA Loop)."""

from translaterany.config import load_config_from_str
from translaterany.config.model import GatesConfig, QALoopOptions


def test_m8_default_configs() -> None:
    raw = """
    [library]
    path = "/tmp"
    """
    cfg = load_config_from_str(raw)
    assert hasattr(cfg, "gates")
    assert cfg.gates.enabled is True
    assert cfg.gates.max_retries == 2
    qa_opt = cfg.stages.get("qa_loop")
    assert qa_opt is not None
    assert qa_opt.options["max_rounds"] == 2
    assert qa_opt.options["max_extra_calls"] == 30
    assert qa_opt.options["warn_edit_rate_threshold"] == 0.25


def test_gates_config_model() -> None:
    gates = GatesConfig()
    assert gates.enabled is True
    assert gates.max_retries == 2

    custom_gates = GatesConfig(enabled=False, max_retries=5)
    assert custom_gates.enabled is False
    assert custom_gates.max_retries == 5


def test_qa_loop_options_model() -> None:
    opts = QALoopOptions()
    assert opts.max_rounds == 2
    assert opts.max_extra_calls == 30
    assert opts.warn_edit_rate_threshold == 0.25

    custom_opts = QALoopOptions(max_rounds=3, max_extra_calls=50, warn_edit_rate_threshold=0.1)
    assert custom_opts.max_rounds == 3
    assert custom_opts.max_extra_calls == 50
    assert custom_opts.warn_edit_rate_threshold == 0.1


def test_m8_custom_config_toml() -> None:
    raw = """
    [gates]
    enabled = false
    max_retries = 3

    [stages.qa_loop.options]
    max_rounds = 4
    """
    cfg = load_config_from_str(raw)
    assert cfg.gates.enabled is False
    assert cfg.gates.max_retries == 3
    qa_opt = cfg.stages.get("qa_loop")
    assert qa_opt is not None
    assert qa_opt.options["max_rounds"] == 4
    assert qa_opt.options["max_extra_calls"] == 30
    assert qa_opt.options["warn_edit_rate_threshold"] == 0.25
