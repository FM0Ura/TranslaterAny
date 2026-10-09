"""Checagens que dependem da memória da série ou dos limites de leitura."""

from dataclasses import dataclass

from translaterany.checks import lexicon
from translaterany.checks.models import CheckEnv, Finding, LineInput
from translaterany.checks.registry import line_check
from translaterany.checks.text import plain, visible_lines
from translaterany.memory.matching import glossary_matches, matches_term


@dataclass(frozen=True)
class ReadingMeasure:
    cps: float | None  # None quando a duração é <= 0
    max_cpl: int
    lines: int


def measure(text: str, duration_ms: int) -> ReadingMeasure:
    lines = [part for part in visible_lines(text) if part]
    chars = sum(len(part) for part in lines)
    cps = chars * 1000 / duration_ms if duration_ms > 0 else None
    return ReadingMeasure(cps=cps, max_cpl=max((len(p) for p in lines), default=0), lines=len(lines))


@line_check("names", {"dialogue"})
def names(line: LineInput, env: CheckEnv) -> list[Finding]:
    src, tgt = plain(line.source), plain(line.target)
    findings: list[Finding] = []
    for group in env.names:
        forms = [n for n in group if len(n) >= 2]
        if any(matches_term(n, src) for n in forms) and not any(matches_term(n, tgt) for n in forms):
            findings.append(
                Finding(
                    check="names", unit_id=line.id, severity="warn", message=f"nome '{forms[0]}' ausente na tradução"
                )
            )
    return findings


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


@line_check("glossary", {"dialogue", "sign"})
def glossary(line: LineInput, env: CheckEnv) -> list[Finding]:
    src, tgt = plain(line.source), plain(line.target)
    findings: list[Finding] = []
    # formas que pertencem a outro dono (personagem ou outra entrada): um alias ambíguo não prova o termo
    foreign = {_norm(n) for group in env.names for n in group} | {_norm(e.term) for e in env.glossary}
    for entry, matched in glossary_matches(env.glossary, src):
        if _norm(entry.term) not in {_norm(t) for t in matched}:
            if all(_norm(t) in foreign for t in matched):
                continue
        expected = entry.term if entry.keep_original else entry.translation
        if expected and not matches_term(expected, tgt):
            findings.append(
                Finding(
                    check="glossary",
                    unit_id=line.id,
                    severity="warn",
                    message=f"termo '{entry.term}' deveria aparecer como '{expected}'",
                )
            )
    return findings


@line_check("foreign_markers", {"dialogue", "sign"})
def foreign_markers(line: LineInput, env: CheckEnv) -> list[Finding]:
    tgt = plain(line.target)
    findings: list[Finding] = []
    for pattern, label in (
        (lexicon.PT_PT_WORDS, "português europeu"),
        (lexicon.PT_PT_PROGRESSIVE, "português europeu"),
        (lexicon.SPANISH, "espanhol"),
    ):
        match = pattern.search(tgt)
        if match:
            findings.append(
                Finding(
                    check="foreign_markers",
                    unit_id=line.id,
                    severity="warn",
                    message=f"marcador de {label}: '{match.group(0)}'",
                )
            )
    return findings


@line_check("reading_speed", {"dialogue"})
def reading_speed(line: LineInput, env: CheckEnv) -> list[Finding]:
    m = measure(line.target, line.duration_ms)
    lim = env.limits
    findings: list[Finding] = []
    if m.cps is not None and m.cps > lim.max_cps:
        findings.append(
            Finding(
                check="reading_speed",
                unit_id=line.id,
                severity="error",
                message=f"CPS {m.cps:.1f} acima de {lim.max_cps:g}",
                value=round(m.cps, 2),
            )
        )
    if line.composite:  # texto unido de várias unidades: só o CPS faz sentido
        return findings
    if m.max_cpl > lim.max_cpl:
        findings.append(
            Finding(
                check="reading_speed",
                unit_id=line.id,
                severity="error",
                message=f"CPL {m.max_cpl} acima de {lim.max_cpl}",
                value=float(m.max_cpl),
            )
        )
    if m.lines > lim.max_lines:
        findings.append(
            Finding(
                check="reading_speed",
                unit_id=line.id,
                severity="error",
                message=f"linhas: {m.lines} (máximo {lim.max_lines})",
                value=float(m.lines),
            )
        )
    return findings


@line_check("profanity_added", {"dialogue"})
def profanity_added(line: LineInput, env: CheckEnv) -> list[Finding]:
    if lexicon.EN_PROFANITY.search(plain(line.source)):
        return []
    match = lexicon.PT_PROFANITY.search(plain(line.target))
    if not match:
        return []
    return [
        Finding(
            check="profanity_added",
            unit_id=line.id,
            severity="warn",
            message=f"palavrão sem equivalente no original: '{match.group(0)}'",
        )
    ]
