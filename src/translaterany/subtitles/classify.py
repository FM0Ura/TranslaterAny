"""Classificação por regras (tipos de linha) e agrupamento do diálogo em cenas."""

import re
from collections import Counter
from collections.abc import Mapping

from pydantic import BaseModel, Field

from translaterany.subtitles.lyrics import split_bilingual_lyric
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
_LYRIC_TRANSLATION_TOKENS = frozenset({"trans", "translation", "translated", "tl"})
_BILINGUAL_NEIGHBOR_MS = 20_000  # letra bilíngue fraca (romaji curto) só vale ao lado de uma forte
BILINGUAL_LYRIC_RULE = "letra bilíngue romaji/inglês"


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


def is_lyric_translation_style(style: str) -> bool:
    """Estilo de tradução de letra ('OP trans', 'ED Translation'): o token 'trans'/'tl' é uma palavra inteira."""
    return bool(set(style_tokens(style)) & _LYRIC_TRANSLATION_TOKENS)


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
    bilingual: dict[str, tuple[int, bool]] = {}  # uid -> (início em ms, romaji forte)
    for uid in pending:
        unit = by_id[uid]
        positioned = any(_POSITION.search(ev.prefix + "".join(ev.markers)) for ev in (events[i] for i in unit.events))
        if unit.style != main_style and positioned:
            result[uid] = UnitClass(type="sign", uncertain=True, rule="\\pos/\\move fora do estilo principal")
        else:
            result[uid] = UnitClass(type="dialogue", uncertain=False, rule="padrão")
            lyric = split_bilingual_lyric(unit.text)
            if lyric is not None:
                bilingual[uid] = (min(events[i].start_ms for i in unit.events), lyric.strong)

    strong_starts = [start for start, strong in bilingual.values() if strong]
    for uid, (start, strong) in bilingual.items():
        if strong or any(abs(start - other) <= _BILINGUAL_NEIGHBOR_MS for other in strong_starts):
            result[uid] = UnitClass(type="song", uncertain=False, rule=BILINGUAL_LYRIC_RULE)

    counts = Counter(c.type for c in result.values())
    return Classification(
        main_style=main_style,
        units=result,
        counts=dict(sorted(counts.items())),
        scenes=_scenes(doc, result, scene_gap_ms),
    )


class DisambiguatedUnit(BaseModel):
    id: str
    line_type: str
    reason: str = ""


class DisambiguateOutput(BaseModel):
    units: list[DisambiguatedUnit]


def disambiguate_uncertain_units(
    doc: NormalizedDoc,
    cls: Classification,
    client: Any | None,
    model: str = "review",
    scene_gap_ms: int = 5000,
) -> Classification:
    import json
    import logging

    logger = logging.getLogger(__name__)

    uncertain_ids = [uid for uid, ucls in cls.units.items() if ucls.uncertain]
    if not uncertain_ids or client is None:
        return cls

    by_id = {u.id: u for u in doc.units}
    items = [{"id": uid, "style": by_id[uid].style, "text": by_id[uid].text} for uid in uncertain_ids if uid in by_id]

    prompt = (
        "Classify the following ambiguous subtitle units into one of: 'dialogue', 'sign', 'song'.\n"
        "Return valid JSON with the schema: {\"units\": [{\"id\": \"...\", \"line_type\": \"dialogue\"|\"sign\"|\"song\", \"reason\": \"...\"}]}\n\n"
        f"Units to classify:\n{json.dumps(items, ensure_ascii=False)}"
    )

    try:
        if hasattr(client, "generate"):
            from translaterany.llm.client import LLMRequest

            req = LLMRequest(
                model=model,
                instructions="You are an expert anime subtitle classifier. Output valid JSON.",
                prompt=prompt,
                output_type=DisambiguateOutput,
                tag="classify",
            )
            resp = client.generate(req)
            parsed = resp.output
        elif hasattr(client, "complete"):
            content = client.complete(prompt)
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                return cls
            parsed = DisambiguateOutput.model_validate(json.loads(m.group(0)))
        elif callable(client):
            content = client(prompt)
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                return cls
            parsed = DisambiguateOutput.model_validate(json.loads(m.group(0)))
        else:
            return cls

        updated_units = dict(cls.units)
        for item in parsed.units:
            if item.id in updated_units:
                updated_units[item.id] = UnitClass(
                    type=item.line_type,
                    uncertain=False,
                    rule="ai_disambiguate",
                )
        counts = Counter(c.type for c in updated_units.values())
        return Classification(
            main_style=cls.main_style,
            units=updated_units,
            counts=dict(sorted(counts.items())),
            scenes=_scenes(doc, updated_units, scene_gap_ms),
        )
    except Exception as exc:
        logger.warning("Falha na desambiguação de unidades por IA: %s. Mantendo classificação determinística.", exc)
        return cls



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

