"""Protocolo "só edições": o modelo devolve {id, new, reason}; cada edição é validada antes de aplicar."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from translaterany.checks import CheckEnv, LineInput, run_line_checks
from translaterany.checks.snapshots import LineSource
from translaterany.checks.text import plain
from translaterany.subtitles.segments import marker_ids

type RejectReason = Literal["unknown_id", "empty", "unchanged", "markers", "reversal", "worse"]
REJECT_REASONS: tuple[RejectReason, ...] = ("unknown_id", "empty", "unchanged", "markers", "reversal", "worse")
WORSE_CHECKS = frozenset({"markers", "numbers", "negation", "names", "glossary", "profanity_added"})
_SPACES = re.compile(r"\s+")


class LineEdit(BaseModel):
    id: str
    new: str
    reason: str = ""


class EditsResponse(BaseModel):
    edits: list[LineEdit] = Field(default_factory=list)


@dataclass
class EditOutcome:
    texts: dict[str, str]
    applied: dict[str, str] = field(default_factory=dict)
    rejected: dict[str, int] = field(default_factory=lambda: dict.fromkeys(REJECT_REASONS, 0))


def normalize_edit_id(raw: str) -> str:
    return raw.strip().strip("[]").strip()


def _norm(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def _meaning_findings(item: str, text: str, src: LineSource, env: CheckEnv) -> set[str]:
    line = LineInput(id=item, line_type=src.line_type, style=src.style, source=src.source, target=text,
                     duration_ms=src.duration_ms, composite=src.composite)  # fmt: skip
    return {f.check for f in run_line_checks([line], env) if f.check in WORSE_CHECKS}


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
        elif Counter(marker_ids(new)) != Counter(marker_ids(src.source)):
            reason = "markers"
        elif forbidden and item in forbidden and _norm(new) == _norm(forbidden[item]):
            reason = "reversal"
        elif _norm(plain(new)).casefold() == _norm(plain(src.source)).casefold() or (
            _meaning_findings(item, new, src, env) - _meaning_findings(item, current, src, env)
        ):
            reason = "worse"
        if reason is not None:
            outcome.rejected[reason] += 1
            continue
        outcome.texts[item] = new
        outcome.applied[item] = new
    return outcome
