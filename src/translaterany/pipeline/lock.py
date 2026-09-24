"""Lock por série: impede duas execuções simultâneas na mesma série."""

import fcntl
from pathlib import Path
from types import TracebackType
from typing import IO


class SeriesLocked(Exception):  # noqa: N818
    """Outra execução já está processando a série."""


class SeriesLock:
    """Lock do sistema operacional (flock): liberado automaticamente se o processo morrer."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: IO[str] | None = None

    def __enter__(self) -> SeriesLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.close()
            raise SeriesLocked(str(self.path)) from exc
        self._fh = fh
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
