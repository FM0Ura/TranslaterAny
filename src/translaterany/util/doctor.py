"""Verificações de ambiente (comando doctor e pré-voo do run)."""

import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

type CheckStatus = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    message: str


class Check(Protocol):
    name: str

    def run(self) -> CheckResult: ...


@dataclass(frozen=True)
class FunctionCheck:
    name: str
    fn: Callable[[], CheckResult]

    def run(self) -> CheckResult:
        return self.fn()


def python_version_check(minimum: tuple[int, int] = (3, 14)) -> Check:
    def run() -> CheckResult:
        current = sys.version_info[:2]
        version = ".".join(map(str, sys.version_info[:3]))
        if current >= minimum:
            return CheckResult("ok", f"Python {version}")
        return CheckResult("fail", f"Python {version}; é necessário {minimum[0]}.{minimum[1]} ou superior")

    return FunctionCheck("python", run)


def data_dir_check(data_dir: Path) -> Check:
    def run() -> CheckResult:
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=data_dir):
                pass
        except OSError as exc:
            return CheckResult("fail", f"diretório de dados sem permissão de escrita: {data_dir} ({exc})")
        return CheckResult("ok", f"diretório de dados gravável: {data_dir}")

    return FunctionCheck("data_dir", run)


def run_checks(checks: Iterable[Check]) -> list[tuple[str, CheckResult]]:
    results: list[tuple[str, CheckResult]] = []
    for check in checks:
        try:
            result = check.run()
        except Exception as exc:  # uma verificação quebrada não derruba as outras
            result = CheckResult("fail", f"erro ao verificar: {exc}")
        results.append((check.name, result))
    return results


def has_failure(results: Iterable[tuple[str, CheckResult]]) -> bool:
    return any(result.status == "fail" for _, result in results)
