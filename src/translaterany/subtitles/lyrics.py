"""Letras bilíngues 'romaji / inglês' num mesmo evento (estilo de diálogo) e heurística de romaji.

A detecção é deliberadamente conservadora: o diálogo comum nunca deve virar letra. Exige uma linha
inteira de palavras compatíveis com romaji (sem nomes próprios no meio) e uma glosa em inglês com
palavras que não existem em romaji (the, you, my...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from translaterany.subtitles.segments import MARKER_RE

# Sílabas do romaji Hepburn: (consoante)(y)vogal, sokuon antes de consoante, 'n' que não abre sílaba
_ROMAJI_WORD = re.compile(
    r"^(?:(?:[kgszdbpmrhfjvwytn]|ch|sh|ts|ny)?y?[aiueoāīūēō]"
    r"|(?:kk|ss|tt|pp|cch|tch|ssh)y?[aiueo]"
    r"|n(?![aiueoy]))+$"
)
_ENGLISH_STOPWORDS = frozenset(
    "the of and you your my in is with that this for on it at from was will have not but what all can "
    "be are our we i'm i'll don't can't won't there their when where why how who into up out".split()
)
_WORD_SPLIT = re.compile(r"[\s\-]+")
_SEPARATORS = (r"\N", " / ")
_STRONG_ROMAJI_WORDS = 3
_MIN_ROMAJI_WORDS = 2
_MIN_GLOSS_WORDS = 3
_MIN_ROMAJI_LETTERS = 6


@dataclass(frozen=True)
class BilingualLyric:
    romaji: str
    separator: str
    gloss: str
    strong: bool  # romaji com 3+ palavras; as fracas só valem ao lado de uma forte (decide quem chama)


def _bare(word: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", word.lower().replace("’", "'"))


def is_romaji_word(word: str) -> bool:
    w = _bare(word).replace("'", "")
    return bool(w) and bool(_ROMAJI_WORD.match(w))


def _words(text: str) -> list[str]:
    return [w for w in _WORD_SPLIT.split(MARKER_RE.sub("", text).strip()) if _bare(w)]


def _looks_romaji_line(text: str) -> bool:
    """Todas as palavras são romaji e só a primeira pode começar com maiúscula (sem nomes próprios)."""
    words = _words(text)
    if len(words) < _MIN_ROMAJI_WORDS or any(ch.isdigit() for ch in MARKER_RE.sub("", text)):
        return False
    if sum(len(_bare(w)) for w in words) < _MIN_ROMAJI_LETTERS:
        return False
    if any(_bare(w) in _ENGLISH_STOPWORDS for w in words):
        return False
    if any(w[:1].isupper() for w in words[1:]):
        return False
    return all(is_romaji_word(w) for w in words)


def _looks_english_gloss(text: str) -> bool:
    words = _words(text)
    if len(words) < _MIN_GLOSS_WORDS:
        return False
    foreign = [w for w in words if not is_romaji_word(w)]
    has_stopword = any(_bare(w) in _ENGLISH_STOPWORDS for w in words)
    return len(foreign) * 2 >= len(words) and (has_stopword or len(foreign) >= 2)


def split_bilingual_lyric(text: str) -> BilingualLyric | None:
    """Devolve (romaji, separador, glosa) se o texto for 'romaji\\Ninglês' ou 'romaji / inglês'."""
    for sep in _SEPARATORS:
        if text.count(sep) != 1:
            continue
        # a outra forma de quebra não pode aparecer: três linhas é ambíguo (diálogo com quebra)
        if any(other in text for other in _SEPARATORS if other != sep):
            return None
        romaji, gloss = (part.strip() for part in text.split(sep))
        if _looks_romaji_line(romaji) and _looks_english_gloss(gloss):
            return BilingualLyric(romaji, sep, gloss, strong=len(_words(romaji)) >= _STRONG_ROMAJI_WORDS)
    return None
