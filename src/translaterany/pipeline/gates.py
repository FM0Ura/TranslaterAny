"""Motor de Portão por Etapa (StageGate) e Escalonamento (M8).

Validação imediata na saída de etapas com IA, contendo erros críticos
com feedback pontual, bloco unitário, detecção de oscilação e salvaguarda 'nunca piorar'.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from translaterany.checks.models import CheckEnv, Finding, LineInput
from translaterany.checks.registry import run_line_checks
from translaterany.config.model import GatesConfig

BLOCKING_CHECKS: frozenset[str] = frozenset({
    "prompt_leak",
    "markers_broken",
    "format_mismatch",
    "untranslated",
    "glossary_violation",
    "cpl_lines_exceeded",
})

_CHECK_ALIASES: dict[str, str] = {
    "markers": "markers_broken",
    "glossary": "glossary_violation",
}


def is_blocking(finding: Finding) -> bool:
    """Verifica se um achado é considerado bloqueante para o portão de etapa."""
    if finding.check in BLOCKING_CHECKS:
        return True
    if _CHECK_ALIASES.get(finding.check) in BLOCKING_CHECKS:
        return True
    if finding.check == "reading_speed":
        msg = finding.message.lower()
        if "cpl" in msg or "linhas" in msg:
            return True
    return False


def filter_blocking_findings(findings: Sequence[Finding]) -> list[Finding]:
    """Filtra exclusivamente os achados severos que bloqueiam o avanço no portão."""
    return [f for f in findings if is_blocking(f)]


def severity_score(findings: Sequence[Finding]) -> int:
    """Calcula a pontuação de severidade dos achados (error = 10, warn/warning = 1)."""
    score = 0
    for f in findings:
        if f.severity == "error":
            score += 10
        elif f.severity in ("warn", "warning"):
            score += 1
    return score


@dataclass
class GateDecision:
    """Decisão emitida pelo StageGate após inspecionar o lote ou fala."""

    passed: bool
    blocking: list[Finding] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    score: int = 0
    action: str = "pass"
    feedback: str = ""

    def __bool__(self) -> bool:
        return self.passed


class StageGate:
    """Motor de portão por etapa com detecção de oscilação e critério 'nunca piorar'."""

    def __init__(
        self,
        max_retries: int = 2,
        enabled: bool = True,
        config: GatesConfig | None = None,
    ) -> None:
        if config is not None:
            self.max_retries = config.max_retries
            self.enabled = config.enabled
        else:
            self.max_retries = max_retries
            self.enabled = enabled
        self.seen_hashes: dict[str, set[str]] = {}

    def text_hash(self, text: str) -> str:
        """Gera hash SHA-256 normalizado para rastreamento de oscilação."""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def is_oscillating(self, unit_id: str, text: str) -> bool:
        """Verifica se o texto gerado para uma unidade já foi visto anteriormente nesta etapa."""
        h = self.text_hash(text)
        hashes = self.seen_hashes.setdefault(unit_id, set())
        if h in hashes:
            return True
        hashes.add(h)
        return False

    def evaluate(self, lines: Sequence[LineInput], env: CheckEnv) -> GateDecision:
        """Avalia um conjunto de linhas com checagens determinísticas e filtra erros bloqueantes."""
        if not self.enabled:
            return GateDecision(passed=True, blocking=[], findings=[], score=0, action="pass", feedback="")

        findings = run_line_checks(lines, env)
        blocking = filter_blocking_findings(findings)
        score = severity_score(findings)
        passed = len(blocking) == 0
        feedback = self.generate_feedback(blocking) if blocking else ""
        action = "pass" if passed else "retry_feedback"

        return GateDecision(
            passed=passed,
            blocking=blocking,
            findings=findings,
            score=score,
            action=action,
            feedback=feedback,
        )

    def generate_feedback(self, findings: Sequence[Finding]) -> str:
        """Gera feedback pontual em PT-BR para reaplicar no prompt da LLM."""
        if not findings:
            return ""
        lines = ["Erros críticos detectados na saída anterior que DEVEM ser corrigidos:"]
        for f in findings:
            prefix = f"[{f.unit_id}] " if f.unit_id else ""
            lines.append(f"- {prefix}{f.message}")
        lines.append(
            "Certifique-se de manter todos os marcadores ⟦n⟧ intactos, não vazar instruções do prompt "
            "e respeitar estritamente o glossário."
        )
        return "\n".join(lines)

    def never_worsen(
        self,
        current_text: str,
        current_findings: Sequence[Finding],
        new_text: str,
        new_findings: Sequence[Finding],
    ) -> tuple[str, Sequence[Finding]]:
        """Aplica a regra 'Nunca Piorar': se a nova versão degradar a severidade, descarta-a."""
        if severity_score(new_findings) <= severity_score(current_findings):
            return new_text, new_findings
        return current_text, current_findings

    def pick_best(
        self,
        candidates: Sequence[tuple[str, Sequence[Finding]]],
    ) -> tuple[str, Sequence[Finding]]:
        """Adota deterministamente a versão candidata com menor severidade acumulada."""
        if not candidates:
            raise ValueError("Lista de candidatos não pode ser vazia")
        return min(candidates, key=lambda c: severity_score(c[1]))

    def reset(self) -> None:
        """Limpa o histórico de hashes vistos."""
        self.seen_hashes.clear()
