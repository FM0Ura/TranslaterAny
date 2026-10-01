"""Testes de checagens exclusivas do resultado final da legenda."""

from translaterany.checks.final_qa import (
    check_ass_syntax,
    check_event_integrity,
    check_timing_bounds,
)
from translaterany.checks.models import CheckEnv
from translaterany.config.model import ChecksConfig


def test_check_ass_syntax_unbalanced_braces() -> None:
    findings = check_ass_syntax("u1", r"{\pos(100,200)Texto sem fechar chave")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_double_linebreaks() -> None:
    findings = check_ass_syntax("u2", r"Primeira linha\N\NSegunda linha")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_valid() -> None:
    findings = check_ass_syntax("u3", r"{\an8}Texto correto\Nsegunda linha.")
    assert len(findings) == 0


def test_check_timing_bounds_invalid() -> None:
    findings = check_timing_bounds("u1", start_ms=5000, end_ms=4000)
    assert any(f.check == "timing_bounds" for f in findings)


def test_check_ass_syntax_unopened_brace() -> None:
    findings = check_ass_syntax("u4", r"Texto com fechamento} sem abertura")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_nested_braces() -> None:
    findings = check_ass_syntax("u5", r"{\an8{\pos(10,10)}}Texto")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_invalid_command() -> None:
    findings = check_ass_syntax("u6", r"{\comandoInvalido}Texto")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_invalid_escape() -> None:
    findings = check_ass_syntax("u7", r"Texto com barra solta \x fora de tag")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_disabled_in_env() -> None:
    env = CheckEnv(limits=ChecksConfig(disabled=["ass_syntax"]))
    findings = check_ass_syntax("u8", r"{\pos(100,200)Texto quebrado", env=env)
    assert len(findings) == 0


def test_check_timing_bounds_valid() -> None:
    findings = check_timing_bounds("u1", start_ms=1000, end_ms=3000)
    assert len(findings) == 0


def test_check_timing_bounds_negative() -> None:
    findings = check_timing_bounds("u2", start_ms=-100, end_ms=2000)
    assert any(f.check == "timing_bounds" for f in findings)


def test_check_timing_bounds_zero_duration() -> None:
    findings = check_timing_bounds("u3", start_ms=2000, end_ms=2000)
    assert any(f.check == "timing_bounds" for f in findings)


def test_check_timing_bounds_disabled_in_env() -> None:
    env = CheckEnv(limits=ChecksConfig(disabled=["timing_bounds"]))
    findings = check_timing_bounds("u4", start_ms=5000, end_ms=4000, env=env)
    assert len(findings) == 0


def test_check_event_integrity_equal() -> None:
    findings = check_event_integrity(expected_count=50, actual_count=50)
    assert len(findings) == 0


def test_check_event_integrity_loss() -> None:
    findings = check_event_integrity(expected_count=50, actual_count=48)
    assert any(f.check == "event_integrity" and f.severity == "error" for f in findings)


def test_check_event_integrity_extra() -> None:
    findings = check_event_integrity(expected_count=50, actual_count=52)
    assert any(f.check == "event_integrity" for f in findings)


def test_check_event_integrity_disabled_in_env() -> None:
    env = CheckEnv(limits=ChecksConfig(disabled=["event_integrity"]))
    findings = check_event_integrity(expected_count=50, actual_count=40, env=env)
    assert len(findings) == 0
