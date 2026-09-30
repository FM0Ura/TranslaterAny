"""Cena de cada fala (por id simples ou composto) e agrupamento por cena para chamadas de IA."""

from collections.abc import Iterable, Mapping, Sequence

from translaterany.subtitles.classify import Scene


def scene_index_of(
    ids: Iterable[str],
    members: Mapping[str, list[str]],
    unit_events: Mapping[str, list[int]],
    scenes: Sequence[Scene],
) -> dict[str, int]:
    """Índice da cena do 1º evento da 1ª unidade de cada id; sem cena (ou sem evento) -> len(scenes)."""
    scene_of_event = {ev: i for i, sc in enumerate(scenes) for ev in sc.events}
    result: dict[str, int] = {}
    for item in ids:
        units = members.get(item, [item])
        events = unit_events.get(units[0], []) if units else []
        result[item] = scene_of_event.get(events[0], len(scenes)) if events else len(scenes)
    return result


def group_by_scene(ids: Sequence[str], scene_of: Mapping[str, int], max_lines: int) -> list[list[str]]:
    by_scene: dict[int, list[str]] = {}
    for item in ids:
        by_scene.setdefault(scene_of.get(item, 1 << 30), []).append(item)
    step = max(1, max_lines)
    return [group[i : i + step] for _, group in sorted(by_scene.items()) for i in range(0, len(group), step)]
