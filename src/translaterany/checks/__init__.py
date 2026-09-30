"""Checagens determinísticas (sem IA, sem I/O), reutilizadas por métricas, triagem, portões e QA."""

from translaterany.checks import rules_basic, rules_context  # noqa: F401 — registra as checagens
from translaterany.checks.models import CheckEnv, Finding, LineInput, Severity
from translaterany.checks.registry import CHECKS, check_names, run_line_checks

__all__ = ["CHECKS", "CheckEnv", "Finding", "LineInput", "Severity", "check_names", "run_line_checks"]
