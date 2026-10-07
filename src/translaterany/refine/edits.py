"""Protocolo "só edições": o modelo devolve {id, new, reason}; cada edição é validada antes de aplicar."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from translaterany.checks import CheckEnv, LineInput, run_line_checks
from translaterany.checks.snapshots import LineSource
from translaterany.checks.text import plain
from translaterany.memory.matching import matches_term
from translaterany.subtitles.segments import marker_ids

type RejectReason = Literal["unknown_id", "empty", "unchanged", "markers", "reversal", "worse", "glossary"]
REJECT_REASONS: tuple[RejectReason, ...] = (
    "unknown_id",
    "empty",
    "unchanged",
    "markers",
    "reversal",
    "worse",
    "glossary",
)
WORSE_CHECKS = frozenset({"markers", "numbers", "negation", "names", "glossary", "profanity_added"})
_SPACES = re.compile(r"\s+")
MIN_LENGTH_RATIO = 0.5  # uma edição com menos da metade do texto visível é tratada como fragmento
MIN_LENGTH_CHECKED = 10


class LineEdit(BaseModel):
    id: str
    new: str = Field(default="", validation_alias=AliasChoices("new", "text"))
    reason: str = ""

    @property
    def text(self) -> str:
        return self.new


class EditsResponse(BaseModel):
    edits: list[LineEdit] = Field(default_factory=list)


@dataclass
class EditOutcome:
    texts: dict[str, str]
    applied: dict[str, str] = field(default_factory=dict)
    rejected: dict[str, int] = field(default_factory=lambda: dict.fromkeys(REJECT_REASONS, 0))


def normalize_edit_id(raw: str) -> str:
    return _SPACES.sub("", raw.strip().strip("[]"))


def _norm(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def _is_fragment(current: str, new: str) -> bool:
    before = len(_norm(plain(current)))
    return before >= MIN_LENGTH_CHECKED and len(_norm(plain(new))) < MIN_LENGTH_RATIO * before


def _meaning_findings(item: str, text: str, src: LineSource, env: CheckEnv) -> set[str]:
    line = LineInput(id=item, line_type=src.line_type, style=src.style, source=src.source, target=text,
                     duration_ms=src.duration_ms, composite=src.composite)  # fmt: skip
    return {f.check for f in run_line_checks([line], env) if f.check in WORSE_CHECKS}


def _drops_glossary_form(current: str, new: str, source: str, env: CheckEnv) -> bool:
    """A edição remove a forma canônica de um termo do glossário (presente na fonte) que o texto atual tinha."""
    src, before, after = plain(source), plain(current), plain(new)
    for entry in env.glossary:
        if not any(matches_term(t, src) for t in (entry.term, *entry.aliases)):
            continue
        expected = entry.term if entry.keep_original else entry.translation
        if expected and matches_term(expected, before) and not matches_term(expected, after):
            return True
    return False


def apply_edits(
    texts: Mapping[str, str],
    edits: Iterable[LineEdit],
    targets: set[str],
    sources: Mapping[str, LineSource],
    env: CheckEnv,
    forbidden: Mapping[str, str] | None = None,
) -> EditOutcome:
    outcome = EditOutcome(texts=dict(texts))
    latest: dict[str, str] = {}
    unknown = 0
    for edit in edits:
        item = normalize_edit_id(edit.id)
        if item not in targets or item not in texts or item not in sources:
            unknown += 1
            continue
        latest[item] = edit.new
    outcome.rejected["unknown_id"] = unknown
    for item, new in latest.items():
        current, src = texts[item], sources[item]
        reason: RejectReason | None = None
        if not new.strip():
            reason = "empty"
        elif _norm(new) == _norm(current):
            reason = "unchanged"
        elif (
            "{" in new
            or "}" in new
            or "⟦" in re.sub(r"⟦\d+⟧", "", new)
            or "⟧" in re.sub(r"⟦\d+⟧", "", new)
            or marker_ids(new) != marker_ids(src.source)
        ):
            reason = "markers"
        elif forbidden and item in forbidden and _norm(new) == _norm(forbidden[item]):
            reason = "reversal"
        elif _drops_glossary_form(current, new, src.source, env):
            reason = "glossary"
        elif (
            _is_fragment(current, new)
            or _norm(plain(new)).casefold() == _norm(plain(src.source)).casefold()
            or (_meaning_findings(item, new, src, env) - _meaning_findings(item, current, src, env))
        ):
            reason = "worse"
        if reason is not None:
            outcome.rejected[reason] += 1
            continue
        outcome.texts[item] = _norm(new)
        outcome.applied[item] = _norm(new)
    return outcome
