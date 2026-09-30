"""Checagens básicas de linha: marcadores, não traduzida, tamanho, números e negação."""

from collections import Counter

from translaterany.checks import lexicon
from translaterany.checks.models import CheckEnv, Finding, LineInput
from translaterany.checks.registry import line_check
from translaterany.checks.text import plain, words
from translaterany.pipeline.units import LINE_TYPES
from translaterany.subtitles.segments import marker_ids


@line_check("markers", LINE_TYPES)
def markers(line: LineInput, env: CheckEnv) -> list[Finding]:
    expected, got = Counter(marker_ids(line.source)), Counter(marker_ids(line.target))
    if expected == got:
        return []
    return [
        Finding(
            check="markers",
            unit_id=line.id,
            severity="error",
            message=f"marcadores divergentes: esperado {sorted(expected.elements())}, obtido {sorted(got.elements())}",
        )
    ]


@line_check("untranslated", {"dialogue", "sign"})
def untranslated(line: LineInput, env: CheckEnv) -> list[Finding]:
    src_words, tgt_words = words(line.source), words(line.target)
    if len(src_words) >= 2 and plain(line.source).casefold().split() == plain(line.target).casefold().split():
        return [Finding(check="untranslated", unit_id=line.id, severity="error", message="linha idêntica ao original")]
    if len(tgt_words) >= 3:
        ratio = sum(w in lexicon.EN_FUNCTION_WORDS for w in tgt_words) / len(tgt_words)
        if ratio >= 0.5:
            return [
                Finding(
                    check="untranslated",
                    unit_id=line.id,
                    severity="error",
                    message=f"texto parece estar em inglês ({ratio:.0%} de palavras funcionais inglesas)",
                    value=round(ratio, 3),
                )
            ]
    return []


@line_check("length_ratio", {"dialogue"})
def length_ratio(line: LineInput, env: CheckEnv) -> list[Finding]:
    src, tgt = plain(line.source), plain(line.target)
    if len(src) < env.limits.length_ratio_min_chars:
        return []
    ratio = len(tgt) / len(src)
    low, high = env.limits.length_ratio
    if low <= ratio <= high:
        return []
    return [
        Finding(
            check="length_ratio",
            unit_id=line.id,
            severity="warn",
            message=f"tamanho anômalo: tradução com {ratio:.2f}× o original",
            value=round(ratio, 3),
        )
    ]


@line_check("numbers", {"dialogue", "sign"})
def numbers(line: LineInput, env: CheckEnv) -> list[Finding]:
    missing = sorted(set(lexicon.DIGITS.findall(plain(line.source))) - set(lexicon.DIGITS.findall(plain(line.target))))
    if not missing:
        return []
    return [
        Finding(
            check="numbers", unit_id=line.id, severity="warn", message=f"número(s) ausente(s): {', '.join(missing)}"
        )
    ]


@line_check("negation", {"dialogue"})
def negation(line: LineInput, env: CheckEnv) -> list[Finding]:
    if lexicon.EN_NEGATION.search(plain(line.source)) and not lexicon.PT_NEGATION.search(plain(line.target)):
        return [
            Finding(check="negation", unit_id=line.id, severity="warn", message="negação do original sumiu na tradução")
        ]
    return []
