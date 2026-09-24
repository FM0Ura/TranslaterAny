from pathlib import Path

import pytest

from translaterany.pipeline.lock import SeriesLock, SeriesLocked


def test_second_acquisition_fails_and_release_allows_again(tmp_path: Path) -> None:
    path = tmp_path / "s" / ".lock"
    with SeriesLock(path):
        with pytest.raises(SeriesLocked):
            with SeriesLock(path):
                pass
    with SeriesLock(path):  # liberado após o primeiro sair
        pass


def test_lock_released_on_exception(tmp_path: Path) -> None:
    path = tmp_path / ".lock"
    with pytest.raises(RuntimeError):
        with SeriesLock(path):
            raise RuntimeError("x")
    with SeriesLock(path):
        pass
