"""Agrupamento por cena compartilhado (M6) e memória por texto."""

from pathlib import Path

from translaterany.memory.matching import load_all_characters, load_memory_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.scenes import group_by_scene, scene_index_of

SCENES = [Scene(id="s1", start_ms=0, end_ms=1, events=[0, 1, 2]), Scene(id="s2", start_ms=2, end_ms=3, events=[3])]
EVENTS = {"u1": [0], "u2": [1], "u3": [2], "u4": [3], "u5": [9]}


def test_scene_index_handles_composites_and_plain_ids() -> None:
    members = {"u2+u3": ["u2", "u3"]}
    got = scene_index_of(["u1", "u2+u3", "u4", "u5", "u9"], members, EVENTS, SCENES)
    assert got == {"u1": 0, "u2+u3": 0, "u4": 1, "u5": 2, "u9": 2}  # u5 fora de cena; u9 sem evento


def test_group_by_scene_keeps_order_and_slices() -> None:
    scene_of = {"u1": 0, "u2+u3": 0, "u4": 1, "u5": 2}
    assert group_by_scene(["u1", "u2+u3", "u4", "u5"], scene_of, 30) == [["u1", "u2+u3"], ["u4"], ["u5"]]
    assert group_by_scene(["u1", "u2+u3", "u4"], scene_of, 1) == [["u1"], ["u2+u3"], ["u4"]]


def test_load_memory_for_text(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    assert load_memory_for_text(None, "s", "x") == ([], [])
    assert load_memory_for_text(store, "s", "x") == ([], [])
    mem = MemoryStore(store.series_dir("s") / "memory")
    mem.save_glossary([GlossaryEntry(term="Ability", translation="Habilidade")])
    mem.save_characters([CharacterEntry(name="Yu"), CharacterEntry(name="Nao")])
    glossary, chars = load_memory_for_text(store, "s", "Yu used an Ability")
    assert [g.term for g in glossary] == ["Ability"] and [c.name for c in chars] == ["Yu"]


def test_load_all_characters(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    assert load_all_characters(None, "s") == []
    assert load_all_characters(store, "s") == []
    mem = MemoryStore(store.series_dir("s") / "memory")
    mem.save_characters([CharacterEntry(name="Yu"), CharacterEntry(name="Nao")])
    all_chars = load_all_characters(store, "s")
    assert [c.name for c in all_chars] == ["Yu", "Nao"]

