"""Triagem sem IA: destaques para a revisão de sentido e alvos da coloquialidade."""

from collections.abc import Mapping, Sequence

from translaterany.checks import CheckEnv, LineInput, run_line_checks
from translaterany.checks.text import plain
from translaterany.refine import lexicon

MEANING_SIGNALS = frozenset(
    {"negation", "numbers", "names", "glossary", "length_ratio", "untranslated", "profanity_added"}
)


def meaning_signals(lines: Sequence[LineInput], env: CheckEnv) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for f in run_line_checks(lines, env):
        if f.check in MEANING_SIGNALS and f.unit_id is not None:
            found.setdefault(f.unit_id, set()).add(f.check)
    return {k: sorted(v) for k, v in found.items()}


def colloquial_signals(
    lines: Sequence[LineInput], speaker_of: Mapping[str, str], speakers_with_style: set[str]
) -> dict[str, list[str]]:
    """Escolhe as falas que a etapa colloquial pode reescrever, com os sinais que as motivaram.

    Só entra a fala com algum sinal de texto duro ou literal (conectivo formal, ênclise, sujeito
    redundante, pronome arcaico, tradução longa demais). O estilo de fala do personagem NÃO seleciona
    sozinho: quando todo personagem tem estilo, o sinal marcaria quase toda fala e a etapa viraria
    reescrita geral, com muita troca lateral de sinônimos e risco de mudar o sentido. Ele só é
    anexado, como sinal de reforço, às falas já escolhidas, e o prompt da etapa o recebe junto
    com o "tom" e o "falante" para orientar a reescrita.
    """
    result: dict[str, list[str]] = {}
    for line in lines:
        pt, en = plain(line.target), plain(line.source)
        signals: list[str] = []
        if lexicon.FORMAL_CONNECTIVE.search(pt):
            signals.append("formal_connective")
        if lexicon.ENCLISIS.search(pt):
            signals.append("enclisis")
        if lexicon.REDUNDANT_SUBJECT.search(pt):
            signals.append("redundant_subject")
        if lexicon.ARCHAIC_PRONOUN.search(pt):
            signals.append("archaic_pronoun")
        if len(en) >= lexicon.TOO_LONG_MIN_CHARS and len(pt) > lexicon.TOO_LONG_RATIO * len(en):
            signals.append("too_long")
        if signals and speaker_of.get(line.id) in speakers_with_style:
            signals.append("speech_style")
        if signals:
            result[line.id] = signals
    return result
