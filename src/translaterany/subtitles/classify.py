"""Classificação por regras (tipos de linha) e agrupamento do diálogo em cenas."""

import re
from collections import Counter
from collections.abc import Mapping

from pydantic import BaseModel, Field

from translaterany.subtitles.normalize import EventInfo, NormalizedDoc

TRANSLATABLE = frozenset({"dialogue", "sign", "song"})
_TOKENS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_KARAOKE = re.compile(r"\\[kK][fo]?\d")
_POSITION = re.compile(r"\\(pos|move)\(")
_STYLE_RULES: dict[str, frozenset[str]] = {
    "romaji": frozenset({"rom", "romaji", "ro"}),
    "song": frozenset(
        {"op", "ed", "in", "ins", "insert", "song", "songs", "lyric", "lyrics", "opening", "ending", "karaoke"}
    ),
    "sign": frozenset({"sign", "signs", "ts", "typeset", "title", "card", "note", "screen"}),
}
_IN_NUMBER = re.compile(r"^in\d+$")


class UnitClass(BaseModel):
    type: str
    uncertain: bool
    rule: str


class Scene(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    events: list[int]


class Classification(BaseModel):
    main_style: str | None
    units: dict[str, UnitClass]
    counts: dict[str, int]
    scenes: list[Scene]


class ClassifiedUnit(BaseModel):
    id: str
    line_type: str = "dialogue"
    raw_text: str = ""
    clean_text: str = ""
    prefix: str = ""
    suffix: str = ""
    start_ms: int = 0
    end_ms: int = 0
    style: str = "Default"
    actor: str = ""
    layer: int = 0


class ClassifiedUnitCollection(BaseModel):
    units: list[ClassifiedUnit] = Field(default_factory=list)


def style_tokens(style: str) -> list[str]:
    """'CharlotteEDEnglish' -> ['charlotte', 'ed', 'english']; 'OP - Romaji 2' -> ['op', 'romaji', '2']."""
    tokens = [t.lower() for t in _TOKENS.findall(style)]
    joined: list[str] = []
    for token in tokens:  # 'IN' + '01' -> também 'in01'
        if joined and token.isdigit() and joined[-1] == "in":
            joined.append("in" + token)
        joined.append(token)
    return joined


def style_categories(style: str) -> set[str]:
    tokens = set(style_tokens(style))
    found = {cat for cat, words in _STYLE_RULES.items() if tokens & words}
    if any(_IN_NUMBER.match(t) for t in tokens):
        found.add("song")
    return found


def classify(doc: NormalizedDoc, overrides: Mapping[str, str], scene_gap_ms: int = 5000) -> Classification:
    events = {ev.index: ev for ev in doc.events}
    result: dict[str, UnitClass] = {}
    pending: list[str] = []  # sem regra de estilo: diálogo ou placa (decidido pelo estilo principal)

    for unit in doc.units:
        unit_events = [events[i] for i in unit.events]
        if unit.style in overrides:
            result[unit.id] = UnitClass(type=overrides[unit.style], uncertain=False, rule="series.toml")
            continue
        if any(_KARAOKE.search(_raw(ev)) for ev in unit_events):
            result[unit.id] = UnitClass(type="karaoke", uncertain=False, rule="tag \\k")
            continue
        cats = style_categories(unit.style)
        conflicting = cats - ({"song"} if "romaji" in cats else set())
        uncertain = len(conflicting) > 1
        for kind in ("romaji", "song", "sign"):
            if kind in cats:
                result[unit.id] = UnitClass(type=kind, uncertain=uncertain, rule=f"estilo '{unit.style}'")
                break
        else:
            pending.append(unit.id)

    by_id = {u.id: u for u in doc.units}
    style_count = Counter(by_id[uid].style for uid in pending)
    main_style = style_count.most_common(1)[0][0] if style_count else None
    for uid in pending:
        unit = by_id[uid]
        positioned = any(_POSITION.search(ev.prefix + "".join(ev.markers)) for ev in (events[i] for i in unit.events))
        if unit.style != main_style and positioned:
            result[uid] = UnitClass(type="sign", uncertain=True, rule="\\pos/\\move fora do estilo principal")
        else:
            result[uid] = UnitClass(type="dialogue", uncertain=False, rule="padrão")

    counts = Counter(c.type for c in result.values())
    return Classification(
        main_style=main_style,
        units=result,
        counts=dict(sorted(counts.items())),
        scenes=_scenes(doc, result, scene_gap_ms),
    )


def _raw(ev: EventInfo) -> str:
    return ev.prefix + "".join(ev.markers) + ev.suffix


def _scenes(doc: NormalizedDoc, classes: Mapping[str, UnitClass], gap_ms: int) -> list[Scene]:
    dialogue = sorted(
        (ev for ev in doc.events if ev.unit is not None and classes[ev.unit].type == "dialogue"),
        key=lambda ev: (ev.start_ms, ev.index),
    )
    scenes: list[Scene] = []
    for ev in dialogue:
        if scenes and ev.start_ms - scenes[-1].end_ms <= gap_ms:
            scenes[-1].events.append(ev.index)
            scenes[-1].end_ms = max(scenes[-1].end_ms, ev.end_ms)
        else:
            scenes.append(Scene(id=f"s{len(scenes) + 1}", start_ms=ev.start_ms, end_ms=ev.end_ms, events=[ev.index]))
    return scenes
