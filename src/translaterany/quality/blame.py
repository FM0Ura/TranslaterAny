"""Algoritmo de Atribuição de Culpa (Blame) para o QA (M8).

Inspeciona o histórico cronológico de instantâneos de texto para localizar
a etapa exata de origem onde o defeito se manifestou pela primeira vez.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from translaterany.checks.final_qa import check_ass_syntax
from translaterany.checks.models import CheckEnv, Finding, LineInput
from translaterany.checks.registry import CHECKS

DEFAULT_FALLBACK_STAGE = "redistribute_sentences"

_CHECK_ALIASES: dict[str, str] = {
    "markers_broken": "markers",
    "glossary_violation": "glossary",
    "cpl_lines_exceeded": "reading_speed",
    "cps": "reading_speed",
}


def _create_line_input(
    unit_id: str,
    text: str,
    sources: Mapping[str, Any] | None,
) -> LineInput:
    source_text = ""
    line_type = "dialogue"
    style = ""
    duration_ms = 0
    composite = False

    if sources is not None and unit_id in sources:
        src_val = sources[unit_id]
        if isinstance(src_val, str):
            source_text = src_val
        elif hasattr(src_val, "source"):
            source_text = getattr(src_val, "source", "")
            line_type = getattr(src_val, "line_type", "dialogue")
            style = getattr(src_val, "style", "")
            duration_ms = getattr(src_val, "duration_ms", 0)
            composite = getattr(src_val, "composite", False)

    return LineInput(
        id=unit_id,
        line_type=line_type,
        style=style,
        source=source_text,
        target=text,
        duration_ms=duration_ms,
        composite=composite,
    )


def _check_unit_fails(
    unit_id: str,
    text: str,
    finding: Finding,
    env: CheckEnv,
    sources: Mapping[str, Any] | None,
) -> bool:
    canonical = _CHECK_ALIASES.get(finding.check, finding.check)

    if canonical == "ass_syntax":
        results = check_ass_syntax(unit_id, text, env)
        return any(f.check == "ass_syntax" for f in results)

    if canonical in CHECKS:
        check_obj = CHECKS[canonical]
        line_input = _create_line_input(unit_id, text, sources)
        try:
            results = check_obj.fn(line_input, env)
        except Exception:
            return False

        if finding.check == "cpl_lines_exceeded":
            return any("cpl" in f.message.lower() or "linhas" in f.message.lower() for f in results)
        if finding.check == "cps":
            return any("cps" in f.message.lower() for f in results)

        return any(f.check in (canonical, finding.check) for f in results)

    return False


def attribute_blame(
    unit_id: str,
    finding: Finding,
    history: Sequence[tuple[str, Mapping[str, str]]],
    env: CheckEnv | None = None,
    sources: Mapping[str, Any] | None = None,
) -> str:
    """Percorre o histórico cronológico de artefatos e identifica a etapa causadora do defeito.

    Avalia a checagem do achado em cada versão do texto da unidade, do instantâneo mais
    antigo ao mais novo. Retorna o nome da primeira etapa em que o defeito se manifestou.
    Se nenhuma etapa intermediária falhar (ex: timing, contagem ou erro exclusivo da finalização),
    retorna 'redistribute_sentences'.
    """
    if not history:
        return DEFAULT_FALLBACK_STAGE

    if env is None:
        env = CheckEnv()

    for stage_name, texts in history:
        if unit_id not in texts:
            continue
        text = texts[unit_id]
        if _check_unit_fails(unit_id, text, finding, env, sources):
            return stage_name

    return DEFAULT_FALLBACK_STAGE
