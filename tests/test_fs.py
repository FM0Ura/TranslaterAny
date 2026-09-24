import os
from pathlib import Path

from translaterany.util.fs import (
    atomic_write,
    atomic_write_text,
    canonical_json,
    cleanup_tmp,
    file_sha256,
    fingerprint,
    slugify,
)


def test_slugify_ascii() -> None:
    assert slugify("Charlotte (2015)").startswith("charlotte-2015-")


def test_slugify_unicode_symbols_become_hyphens() -> None:
    slug = slugify("High School D×D (2012)")
    assert slug.startswith("high-school-d-d-2012-")
    assert "×" not in slug


def test_slugify_star_and_underscores() -> None:
    assert slugify("Levia and So ☆ __x").startswith("levia-and-so-x-")


def test_slugify_is_stable_and_distinguishes_collisions() -> None:
    assert slugify("A/B") == slugify("A/B")
    assert slugify("A B") != slugify("A-B")  # mesma base "a-b", sufixos de hash diferentes


def test_slugify_empty_base() -> None:
    assert slugify("☆☆").startswith("x-")


def test_atomic_write_creates_parents_and_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.json"
    atomic_write_text(target, "conteúdo")
    assert target.read_text(encoding="utf-8") == "conteúdo"
    assert list(target.parent.iterdir()) == [target]


def test_atomic_write_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "f.bin"
    atomic_write(target, b"1")
    atomic_write(target, b"2")
    assert target.read_bytes() == b"2"


def test_cleanup_tmp_removes_only_temporaries(tmp_path: Path) -> None:
    keep = tmp_path / "x" / "keep.json"
    atomic_write_text(keep, "{}")
    leftover = keep.with_name(f"keep.json.tmp-{os.getpid() + 1}")
    leftover.write_text("parcial")
    assert cleanup_tmp(tmp_path) == 1
    assert keep.exists() and not leftover.exists()


def test_cleanup_tmp_missing_dir(tmp_path: Path) -> None:
    assert cleanup_tmp(tmp_path / "nao-existe") == 0


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": "é"}) == canonical_json({"a": "é", "b": 1})
    assert canonical_json({"a": "é"}) == '{"a":"é"}'.encode()


def test_file_sha256_prefix(tmp_path: Path) -> None:
    f = tmp_path / "f"
    f.write_bytes(b"abc")
    assert file_sha256(f) == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_fingerprint_changes_with_content_small_file(tmp_path: Path) -> None:
    f = tmp_path / "small.mkv"
    f.write_bytes(b"a" * 100)
    first = fingerprint(f)
    f.write_bytes(b"b" * 100)
    assert fingerprint(f) != first


def test_fingerprint_detects_change_in_tail_of_large_file(tmp_path: Path) -> None:
    f = tmp_path / "big.mkv"
    data = bytearray(b"\0" * (3 * 1024 * 1024))
    f.write_bytes(bytes(data))
    first = fingerprint(f)
    data[-1] = 1
    f.write_bytes(bytes(data))
    assert fingerprint(f) != first


def test_fingerprint_between_one_and_two_mib(tmp_path: Path) -> None:
    f = tmp_path / "mid.mkv"
    data = bytearray(b"\0" * (1024 * 1024 + 10))
    f.write_bytes(bytes(data))
    first = fingerprint(f)
    data[-1] = 1
    f.write_bytes(bytes(data))
    assert fingerprint(f) != first
