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
