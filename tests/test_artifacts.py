from pathlib import Path

import pytest
from pydantic import BaseModel

from translaterany.pipeline.artifacts import OutputWriter


class M(BaseModel):
    a: int


def test_output_json_named_after_stage(tmp_path: Path) -> None:
    writer = OutputWriter(tmp_path, "normalize")
    writer.json(M(a=1))
    assert writer.written == "normalize.json"
    assert writer.path == tmp_path / "normalize.json"
    assert M.model_validate_json((tmp_path / "normalize.json").read_text()).a == 1


def test_output_file_with_suffix(tmp_path: Path) -> None:
    writer = OutputWriter(tmp_path, "write")
    writer.file(".ass", b"[Script Info]")
    assert (tmp_path / "write.ass").read_bytes() == b"[Script Info]"


def test_output_twice_is_error(tmp_path: Path) -> None:
    writer = OutputWriter(tmp_path, "x")
    writer.json(M(a=1))
    with pytest.raises(RuntimeError, match="mais de um"):
        writer.json(M(a=2))


def test_output_suffix_must_start_with_dot(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        OutputWriter(tmp_path, "x").file("ass", b"")
