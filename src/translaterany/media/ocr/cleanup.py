"""Correções determinísticas e conservadoras de confusões típicas do Tesseract em legendas."""

import re

_TAG_BLOCK = re.compile(r"\{[^}]*\}")

# '|' isolado: precedido por início, espaço, quebra \N, fim de tag ASS ou abertura/travessão, e seguido
# por espaço, fim, \N, tag, pontuação ou contração (|'m |'ll |'ve |'d). Dentro de palavras, URLs, karaokê
# ({\k}) e tags ASS o '|' nunca casa.
_ISOLATED_PIPE = re.compile(
    r"(?P<pre>^|\s|\\N|\}|[(\[\"“\-–—])\|(?=$|\s|\\N|\{|[.,!?…:;)\]\"”]|['’][A-Za-z])"
)


def fix_pipe_as_capital_i(text: str) -> str:
    """Troca '|' isolado por 'I' (pronome inglês), preservando marcação de itálico e tags ASS."""
    if "|" not in text:
        return text
    visible = _TAG_BLOCK.sub("", text).replace("\\N", " ")
    if not visible.replace("|", "").strip():
        return text  # linha só de barras: ruído gráfico, não o pronome
    return _ISOLATED_PIPE.sub(lambda m: m.group("pre") + "I", text)
