"""Blocos por cena do M6."""

import json

from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage import Stage
from translaterany.refine.blocks import ReviewLine, build_blocks, render_block_prompt


def test_blocks_by_scene_keep_context_and_drop_scenes_without_targets() -> None:
    ids = ["a", "b", "c", "d", "e"]
    scene_of = {"a": 0, "b": 0, "c": 0, "d": 1, "e": 2}
    assert build_blocks(ids, {"a", "c", "e"}, scene_of, 30) == [["a", "b", "c"], ["e"]]


def test_blocks_limit_targets_per_block() -> None:
    ids = ["a", "b", "c", "d"]
    scene_of = dict.fromkeys(ids, 0)
    assert build_blocks(ids, set(ids), scene_of, 2) == [["a", "b"], ["c", "d"]]


def test_render_block_prompt_is_json_with_flags() -> None:
    line = ReviewLine(id="u1", source="Hi\\Nthere", target="Oi", speaker="Yu", tone="calm", budget=20,
                      signals=["negation"], editable=True)  # fmt: skip
    data = json.loads(render_block_prompt([line]))
    assert data == [{"id": "u1", "en": "Hi there", "pt": "Oi", "falante": "Yu", "tom": "calm",
                     "limite_caracteres": 20, "sinais": ["negation"], "editavel": True}]  # fmt: skip


def test_produces_dialogue_flag() -> None:
    import translaterany.stages  # noqa: F401

    assert Stage.produces_dialogue is False
    assert REGISTRY.get("translate_dialogue").produces_dialogue is True


def test_blocks_slicing_with_max_lines_and_no_context_window_is_pinned() -> None:
    ids = list("abcdefghij")
    scene_of = dict.fromkeys(ids, 0)
    assert build_blocks(ids, {"c", "f", "i"}, scene_of, 1) == [list("abcde"), list("fgh"), list("ij")]


def test_context_window_caps_block_size_in_long_scene() -> None:
    ids = [f"u{i}" for i in range(150)]
    scene_of = dict.fromkeys(ids, 0)
    targets = {"u10", "u70", "u140"}
    blocks = build_blocks(ids, targets, scene_of, 30, context_window=3)
    assert len(blocks) == 1 and len(blocks[0]) <= 3 + 6 * 3
    assert len(set(blocks[0])) == len(blocks[0]) and blocks[0] == sorted(blocks[0], key=ids.index)
    assert "u7" in blocks[0] and "u6" not in blocks[0] and "u13" in blocks[0] and "u14" not in blocks[0]


def test_context_window_overlap_has_no_duplicates_and_respects_scenes_and_max_lines() -> None:
    ids = list("abcdefgh")
    scene_of = {"a": 0, "b": 0, "c": 0, "d": 1, "e": 1, "f": 1, "g": 1, "h": 1}
    assert build_blocks(ids, {"b", "c", "e"}, scene_of, 30, context_window=1) == [list("abc"), list("def")]
    assert build_blocks(ids, {"e", "g"}, scene_of, 1, context_window=1) == [list("def"), list("fgh")]


def test_window_blocks_do_not_make_other_groups_targets_editable_context() -> None:
    ids = list("abcd")
    assert build_blocks(ids, {"b", "c"}, dict.fromkeys(ids, 0), 1, context_window=1) == [list("ab"), list("cd")]
