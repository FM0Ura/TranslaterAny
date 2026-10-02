"""Checagens exclusivas finais do QA pós-redistribuição (M8).

Valida integridade estrutural e sintática do resultado final da legenda (.ass):
- check_ass_syntax: sintaxe de tags ASS, escapes e balanceamento de chaves.
- check_timing_bounds: marcações de tempo ordenadas (início < fim) e duração positiva.
- check_event_integrity: contagem de falas/eventos contra o original para alertar perda.
"""

import re

from translaterany.checks.models import CheckEnv, Finding

_DOUBLE_LINEBREAK_RE = re.compile(r"\\[Nn]\s*\\[Nn]")
_INVALID_ESCAPE_RE = re.compile(r"\\(?:[^Nnh]|\Z)")

# Padrões regex para validação de comandos ASS conhecidos
_TAG_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Comandos com argumentos entre parênteses
    re.compile(r"^(?:pos|move|org|fad|fade|clip|iclip|t)\(.*\)$"),
    # Valores numéricos e dimensões
    re.compile(
        r"^(?:fs|fscx|fscy|fsp|frx|fry|frz|fr|fax|fay|fe|xbord|ybord|bord|xshad|yshad|shad|be|blur|pbo|p|k[fo]?|K)\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)?$"
    ),
    # Flags e seleções inteiras
    re.compile(r"^(?:b|i|u|s)\s*\d*$"),
    re.compile(r"^q\s*[0-3]?$"),
    re.compile(r"^an\s*[1-9]$"),
    re.compile(r"^a\s*(?:[1-9]|1[01])$"),
    # Cores e transparência (ex: \c&HFFFFFF&, \1c&H00&, \alpha&HFF&)
    re.compile(r"^(?:[1-4]?c|alpha|[1-4]a)\s*(?:&[hH][0-9a-fA-F]+&?|[0-9a-fA-F]+)?$"),
    # Fonte e reinicialização de estilo
    re.compile(r"^fn\s*.+$"),
    re.compile(r"^r\s*.*$"),
    # Espaçamento e quebras internas
    re.compile(r"^(?:h|N|n)$"),
)

_PAREN_PREFIXES: tuple[str, ...] = ("pos", "move", "org", "fade", "fad", "clip", "iclip", "t")


def check_ass_syntax(
    unit_id: str,
    text: str,
    env: CheckEnv | None = None,
) -> list[Finding]:
    """Valida sintaxe ASS do texto final: chaves balanceadas, tags conhecidas e ausência de '\\N\\N'."""
    if env is not None and "ass_syntax" in env.limits.disabled:
        return []

    findings: list[Finding] = []

    # 1. Proibir quebras de linha literais (CR/LF) dentro do texto do evento
    if "\n" in text or "\r" in text:
        findings.append(
            Finding(
                check="ass_syntax",
                unit_id=unit_id,
                severity="error",
                message="quebra de linha literal (CR/LF) no texto do evento ASS",
                excerpt=text,
            )
        )

    # 2. Validar quebras de linha consecutivas inválidas (\N\N)
    if _DOUBLE_LINEBREAK_RE.search(text):
        findings.append(
            Finding(
                check="ass_syntax",
                unit_id=unit_id,
                severity="error",
                message="quebras de linha consecutivas inválidas ('\\N\\N')",
                excerpt=text,
            )
        )

    # 3. Validar balanceamento de chaves '{' e '}'
    in_brace = False
    brace_start = -1
    brace_blocks: list[tuple[int, int, str]] = []

    for i, ch in enumerate(text):
        if ch == "{":
            if in_brace:
                findings.append(
                    Finding(
                        check="ass_syntax",
                        unit_id=unit_id,
                        severity="error",
                        message=f"chaves desbalanceadas: abertura '{{' aninhada na posição {i}",
                        excerpt=text[max(0, i - 10) : min(len(text), i + 20)],
                    )
                )
            in_brace = True
            brace_start = i
        elif ch == "}":
            if not in_brace:
                findings.append(
                    Finding(
                        check="ass_syntax",
                        unit_id=unit_id,
                        severity="error",
                        message=f"chaves desbalanceadas: fechamento '}}' sem abertura na posição {i}",
                        excerpt=text[max(0, i - 10) : min(len(text), i + 20)],
                    )
                )
            else:
                in_brace = False
                brace_blocks.append((brace_start, i + 1, text[brace_start + 1 : i]))

    if in_brace:
        findings.append(
            Finding(
                check="ass_syntax",
                unit_id=unit_id,
                severity="error",
                message=f"chaves desbalanceadas: '{{' aberta na posição {brace_start} sem fechamento",
                excerpt=text[max(0, brace_start - 10) : min(len(text), brace_start + 20)],
            )
        )

    # 4. Validar comandos dentro dos blocos {...}
    for _, _, content in brace_blocks:
        content_stripped = content.strip()
        if not content_stripped or not content_stripped.lstrip("\\"):
            findings.append(
                Finding(
                    check="ass_syntax",
                    unit_id=unit_id,
                    severity="error",
                    message=f"bloco de formatação ASS vazio '{{{content}}}'",
                    excerpt=f"{{{content}}}",
                )
            )
            continue

        if not content_stripped.startswith("\\"):
            findings.append(
                Finding(
                    check="ass_syntax",
                    unit_id=unit_id,
                    severity="error",
                    message=f"bloco de formatação ASS não inicia com '\\': '{{{content}}}'",
                    excerpt=f"{{{content}}}",
                )
            )
            continue

        # Separar tags respeitando parênteses de argumentos ex.: \t(0, 500, \fs20)
        tags: list[str] = []
        current: list[str] = []
        paren_depth = 0
        for char in content_stripped[1:]:  # pula a primeira barra
            if char == "(":
                paren_depth += 1
                current.append(char)
            elif char == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    findings.append(
                        Finding(
                            check="ass_syntax",
                            unit_id=unit_id,
                            severity="error",
                            message=f"parênteses desbalanceados no bloco ASS: '{{{content}}}'",
                            excerpt=content,
                        )
                    )
                    paren_depth = 0
                current.append(char)
            elif char == "\\" and paren_depth == 0:
                if current:
                    tags.append("".join(current).strip())
                    current.clear()
            else:
                current.append(char)

        if paren_depth > 0:
            findings.append(
                Finding(
                    check="ass_syntax",
                    unit_id=unit_id,
                    severity="error",
                    message=f"parênteses não fechados no bloco ASS: '{{{content}}}'",
                    excerpt=content,
                )
            )

        if current:
            tags.append("".join(current).strip())

        for tag in tags:
            if not tag:
                continue

            if tag.startswith(_PAREN_PREFIXES) and not re.match(r"^(?:pos|move|org|fad|fade|clip|iclip|t)\(", tag):
                findings.append(
                    Finding(
                        check="ass_syntax",
                        unit_id=unit_id,
                        severity="error",
                        message=f"comando ASS requer argumentos entre parênteses: '\\{tag}'",
                        excerpt=f"\\{tag}",
                    )
                )
            elif not any(pattern.match(tag) for pattern in _TAG_PATTERNS):
                findings.append(
                    Finding(
                        check="ass_syntax",
                        unit_id=unit_id,
                        severity="error",
                        message=f"comando ASS desconhecido ou malformado: '\\{tag}'",
                        excerpt=f"\\{tag}",
                    )
                )

    # 5. Validar integridade de escapes fora dos blocos {...}
    text_without_tags = re.sub(r"\{[^}]*\}", "", text)
    if match := _INVALID_ESCAPE_RE.search(text_without_tags):
        findings.append(
            Finding(
                check="ass_syntax",
                unit_id=unit_id,
                severity="error",
                message=f"escape inválido fora de bloco ASS: '{match.group(0)}'",
                excerpt=text_without_tags,
            )
        )

    return findings


def check_timing_bounds(
    unit_id: str,
    start_ms: int,
    end_ms: int,
    env: CheckEnv | None = None,
    *,
    min_duration_ms: int = 1,
) -> list[Finding]:
    """Assegura ordenação de tempo (start < end) e duração mínima positiva."""
    if env is not None and "timing_bounds" in env.limits.disabled:
        return []

    findings: list[Finding] = []

    if start_ms < 0:
        findings.append(
            Finding(
                check="timing_bounds",
                unit_id=unit_id,
                severity="error",
                message=f"marcação de tempo negativa: início ({start_ms}ms) < 0",
                value=float(start_ms),
            )
        )

    if start_ms >= end_ms:
        findings.append(
            Finding(
                check="timing_bounds",
                unit_id=unit_id,
                severity="error",
                message=f"marcação de tempo invertida ou nula: início ({start_ms}ms) >= fim ({end_ms}ms)",
                value=float(end_ms - start_ms),
            )
        )
    elif (end_ms - start_ms) < min_duration_ms:
        findings.append(
            Finding(
                check="timing_bounds",
                unit_id=unit_id,
                severity="error",
                message=f"duração da legenda insuficiente: {end_ms - start_ms}ms < {min_duration_ms}ms",
                value=float(end_ms - start_ms),
            )
        )

    return findings


def check_event_integrity(
    expected_count: int,
    actual_count: int,
    env: CheckEnv | None = None,
    *,
    unit_id: str | None = None,
) -> list[Finding]:
    """Compara quantidade de falas/eventos entre original e final para alertar perda ou divergência."""
    if env is not None and "event_integrity" in env.limits.disabled:
        return []

    findings: list[Finding] = []

    if actual_count < expected_count:
        lost = expected_count - actual_count
        findings.append(
            Finding(
                check="event_integrity",
                unit_id=unit_id,
                severity="error",
                message=(
                    f"perda de falas/eventos na legenda: esperado {expected_count}, "
                    f"obtido {actual_count} ({lost} ausentes)"
                ),
                value=float(actual_count),
            )
        )
    elif actual_count > expected_count:
        extra = actual_count - expected_count
        findings.append(
            Finding(
                check="event_integrity",
                unit_id=unit_id,
                severity="warn",
                message=(
                    f"divergência na quantidade de falas: esperado {expected_count}, "
                    f"obtido {actual_count} ({extra} a mais)"
                ),
                value=float(actual_count),
            )
        )

    return findings
