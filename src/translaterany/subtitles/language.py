"""Heurística simples: o texto parece inglês?"""

import re

from translaterany.subtitles.ass import AssDocument

_TAGS = re.compile(r"\{[^}]*\}|\\[Nnh]")
_WORDS = re.compile(r"[a-z']+")
COMMON_ENGLISH = frozenset(
    """the be to of and a in that have i it for not on with he as you do at this but his by from they we say her
    she or an will my one all would there their what so up out if about who get which go me when make can like time
    no just him know take people into year your good some could them see other than then now look only come its
    over think also back after use two how our work first well way even new want because any these give day most
    us is are was were am been has had did does don't i'm it's that's you're what's let's here
    yes okay oh hey""".split()
)
THRESHOLD = 0.15


def english_ratio(doc: AssDocument) -> float:
    words = [w for ev in doc.events if ev.kind == "dialogue" for w in _WORDS.findall(_TAGS.sub(" ", ev.text).lower())]
    if not words:
        return 0.0
    return sum(w in COMMON_ENGLISH for w in words) / len(words)


def looks_english(doc: AssDocument) -> bool:
    return english_ratio(doc) >= THRESHOLD
