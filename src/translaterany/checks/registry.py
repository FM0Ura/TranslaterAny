"""Registro das checagens de linha e execução tolerante a falhas."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from translaterany.checks.models import CheckEnv, Finding, LineInput

type CheckFn = Callable[[LineInput, CheckEnv], list[Finding]]

EPISODE_CHECKS: tuple[str, ...] = ("font_glyphs",)


@dataclass(frozen=True)
class LineCheck:
    name: str
    line_types: frozenset[str]
    fn: CheckFn


CHECKS: dict[str, LineCheck] = {}


def line_check(name: str, line_types: Iterable[str]) -> Callable[[CheckFn], CheckFn]:
    def decorator(fn: CheckFn) -> CheckFn:
        CHECKS[name] = LineCheck(name=name, line_types=frozenset(line_types), fn=fn)
        return fn

    return decorator


def check_names() -> set[str]:
    return set(CHECKS) | set(EPISODE_CHECKS)


def run_line_checks(lines: Iterable[LineInput], env: CheckEnv) -> list[Finding]:
    disabled = set(env.limits.disabled)
    findings: list[Finding] = []
    for line in lines:
        for check in CHECKS.values():
            if check.name in disabled or line.line_type not in check.line_types:
                continue
            try:
                findings.extend(check.fn(line, env))
            except Exception as exc:  # checagem com bug não derruba o episódio
                findings.append(
                    Finding(
                        check="check_crashed",
                        unit_id=line.id,
                        severity="error",
                        message=f"checagem '{check.name}' falhou: {type(exc).__name__}: {exc}",
                    )
                )
    return findings
