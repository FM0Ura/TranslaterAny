from pathlib import Path

from translaterany.util.doctor import (
    CheckResult,
    FunctionCheck,
    data_dir_check,
    has_failure,
    python_version_check,
    run_checks,
)


def test_python_version_ok() -> None:
    assert python_version_check((3, 0)).run().status == "ok"


def test_python_version_fail() -> None:
    result = python_version_check((99, 0)).run()
    assert result.status == "fail"
    assert "99.0" in result.message


def test_data_dir_check_creates_dir(tmp_path: Path) -> None:
    target = tmp_path / "novo" / "dados"
    assert data_dir_check(target).run().status == "ok"
    assert target.is_dir()


def test_data_dir_check_fails_when_path_is_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "arquivo"
    blocker.write_text("x")
    assert data_dir_check(blocker / "dados").run().status == "fail"


def test_run_checks_isolates_exceptions() -> None:
    def boom() -> CheckResult:
        raise RuntimeError("quebrou")

    results = run_checks([FunctionCheck("ruim", boom), FunctionCheck("bom", lambda: CheckResult("ok", "ok"))])
    assert [name for name, _ in results] == ["ruim", "bom"]
    assert results[0][1].status == "fail" and "quebrou" in results[0][1].message
    assert has_failure(results)


def test_has_failure_ignores_warnings() -> None:
    assert not has_failure([("a", CheckResult("warn", "atenção"))])
