"""Testes unitários do StageGate e escada de escalonamento."""

from translaterany.checks import CheckEnv, Finding, LineInput
from translaterany.config.model import GatesConfig
from translaterany.pipeline.gates import (
    BLOCKING_CHECKS,
    GateDecision,
    StageGate,
    filter_blocking_findings,
    severity_score,
)


def test_filter_blocking_findings() -> None:
    findings = [
        Finding(unit_id="u1", check="prompt_leak", message="instrução vazada", severity="error"),
        Finding(unit_id="u2", check="cps", message="leitura rápida", severity="warning"),
        Finding(unit_id="u3", check="markers_broken", message="tag perdida", severity="error"),
    ]
    blocking = filter_blocking_findings(findings)
    assert len(blocking) == 2
    assert {f.check for f in blocking} == {"prompt_leak", "markers_broken"}
    assert "prompt_leak" in BLOCKING_CHECKS


def test_filter_blocking_findings_with_real_check_names() -> None:
    findings = [
        Finding(unit_id="u1", check="markers", message="marcadores divergentes", severity="error"),
        Finding(unit_id="u2", check="glossary", message="termo incorreto", severity="warn"),
        Finding(unit_id="u3", check="length_ratio", message="tamanho anômalo", severity="warn"),
        Finding(unit_id="u4", check="reading_speed", message="CPL 45 acima de 37", severity="error"),
        Finding(unit_id="u5", check="reading_speed", message="CPS 25.0 acima de 17", severity="error"),
    ]
    blocking = filter_blocking_findings(findings)
    assert len(blocking) == 3
    assert {f.unit_id for f in blocking} == {"u1", "u2", "u4"}


def test_severity_score_comparison() -> None:
    f_clean: list[Finding] = []
    f_warning = [Finding(unit_id="u1", check="cps", message="aviso", severity="warning")]
    f_severe = [Finding(unit_id="u1", check="prompt_leak", message="erro", severity="error")]
    assert severity_score(f_clean) < severity_score(f_warning) < severity_score(f_severe)
    assert severity_score(f_clean) == 0
    assert severity_score(f_warning) == 1
    assert severity_score(f_severe) == 10


def test_oscillation_detection() -> None:
    gate = StageGate(max_retries=2)
    assert gate.is_oscillating("u1", "Texto A") is False
    assert gate.is_oscillating("u1", "Texto B") is False
    assert gate.is_oscillating("u1", "Texto A") is True


def test_oscillation_detection_per_unit() -> None:
    gate = StageGate()
    assert gate.is_oscillating("u1", "Mesmo texto") is False
    assert gate.is_oscillating("u2", "Mesmo texto") is False
    assert gate.is_oscillating("u1", "Mesmo texto") is True


def test_gate_decision_properties() -> None:
    d_pass = GateDecision(passed=True, blocking=[], score=0)
    assert bool(d_pass) is True

    f_block = [Finding(unit_id="u1", check="prompt_leak", message="vazamento", severity="error")]
    d_fail = GateDecision(passed=False, blocking=f_block, score=10, action="retry_feedback", feedback="Corrija")
    assert bool(d_fail) is False
    assert len(d_fail.blocking) == 1
    assert d_fail.action == "retry_feedback"


def test_gate_evaluate_clean_and_blocking() -> None:
    gate = StageGate()
    env = CheckEnv()

    clean_line = LineInput(
        id="u1",
        line_type="dialogue",
        source="Hello world ⟦1⟧.",
        target="Olá mundo ⟦1⟧.",
        duration_ms=2000,
    )
    decision = gate.evaluate([clean_line], env)
    assert decision.passed is True
    assert len(decision.blocking) == 0
    assert decision.score == 0

    bad_line = LineInput(
        id="u2",
        line_type="dialogue",
        source="Hello world ⟦1⟧.",
        target="[u2] Hello world ⟦1⟧.",  # prompt_leak + untranslated
        duration_ms=2000,
    )
    decision_bad = gate.evaluate([bad_line], env)
    assert decision_bad.passed is False
    assert len(decision_bad.blocking) > 0
    assert "Corrija" in decision_bad.feedback or "Erros críticos" in decision_bad.feedback


def test_never_worsen_preserves_best_candidate() -> None:
    gate = StageGate()
    f_clean: list[Finding] = []
    f_warn = [Finding(unit_id="u1", check="numbers", message="número", severity="warn")]
    f_err = [Finding(unit_id="u1", check="prompt_leak", message="leak", severity="error")]

    # Nova versão piorou -> mantém a original
    text, findings = gate.never_worsen("Versão original", f_warn, "Versão piorada", f_err)
    assert text == "Versão original"
    assert findings == f_warn

    # Nova versão melhorou -> adota a nova versão
    text2, findings2 = gate.never_worsen("Versão com erro", f_err, "Versão limpa", f_clean)
    assert text2 == "Versão limpa"
    assert findings2 == f_clean

    # pick_best escolhe a menor severidade
    candidates = [
        ("v1_err", f_err),
        ("v2_warn", f_warn),
        ("v3_clean", f_clean),
    ]
    best_text, best_findings = gate.pick_best(candidates)
    assert best_text == "v3_clean"
    assert best_findings == f_clean


def test_gate_disabled_always_passes() -> None:
    gate = StageGate(config=GatesConfig(enabled=False, max_retries=0))
    env = CheckEnv()
    bad_line = LineInput(
        id="u1",
        line_type="dialogue",
        source="Hello ⟦1⟧.",
        target="[u1] Hello ⟦1⟧.",
        duration_ms=2000,
    )
    decision = gate.evaluate([bad_line], env)
    assert decision.passed is True
    assert len(decision.blocking) == 0
