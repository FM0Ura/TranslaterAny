"""Termos do glossário protegidos por marcador ⟦Gn⟧: o modelo não os vê, a forma canônica é reposta depois."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from translaterany.memory.matching import term_spans
from translaterany.memory.models import GlossaryEntry
from translaterany.subtitles.segments import MARKER_RE

PLACEHOLDER_RE = re.compile(r"⟦\s*[Gg](\d+)\s*⟧")  # tolera espaços e caixa alterados pelo modelo
_OPENERS = "\"'“‘«([¿¡-–—"
_DOUBLE_SPACE = re.compile(r" {2,}")


@dataclass
class ProtectedText:
    text: str  # texto com ⟦Gn⟧ no lugar de cada termo
    canonicals: list[str] = field(default_factory=list)  # forma canônica do marcador n (índice n-1)


def _starts_sentence(preceding: str) -> bool:
    before = MARKER_RE.sub("", preceding).rstrip().rstrip(_OPENERS).rstrip()
    if not before:
        return True
    return before[-1] in "!?" or (before[-1] == "." and not before.endswith(".."))


class GlossaryProtector:
    def __init__(self, glossary: Sequence[GlossaryEntry]) -> None:
        self.forms: list[tuple[str, str]] = []  # (forma na fonte, forma canônica na tradução)
        for entry in glossary:
            canonical = entry.term if entry.keep_original else entry.translation
            if not canonical:
                continue
            for form in (entry.term, *entry.aliases):
                if form:
                    self.forms.append((form, canonical))
        self.forms.sort(key=lambda f: -len(f[0]))  # mais longo primeiro: "time leap machine" antes de "machine"

    def __bool__(self) -> bool:
        return bool(self.forms)

    def protect(self, text: str) -> ProtectedText:
        candidates = [(start, end, canon) for form, canon in self.forms for start, end in term_spans(form, text)]
        candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
        taken: list[tuple[int, int, str]] = []
        for start, end, canon in candidates:
            if not any(start < t_end and t_start < end for t_start, t_end, _ in taken):
                taken.append((start, end, canon))
        taken.sort()
        out: list[str] = []
        canonicals: list[str] = []
        pos = 0
        for start, end, canon in taken:
            out.append(text[pos:start])
            if text[start:end] == canon:  # já está na forma canônica: nada a impor, o modelo a mantém
                out.append(text[start:end])
            else:
                canonicals.append(canon)
                out.append(f"⟦G{len(canonicals)}⟧")
            pos = end
        out.append(text[pos:])
        return ProtectedText(text="".join(out), canonicals=canonicals)

    def restore(self, translated: str, canonicals: Sequence[str]) -> tuple[str, bool]:
        """Repõe as formas canônicas. O booleano é False se algum marcador sumiu, duplicou ou é desconhecido."""
        ok = True
        seen: set[int] = set()
        out: list[str] = []
        pos = 0
        for m in PLACEHOLDER_RE.finditer(translated):
            out.append(translated[pos : m.start()])
            index = int(m.group(1))
            if not 1 <= index <= len(canonicals) or index in seen:
                ok = False  # desconhecido ou repetido: o marcador é descartado
            else:
                seen.add(index)
                canon = canonicals[index - 1]
                if canon[:1].islower() and _starts_sentence("".join(out)):
                    canon = canon[0].upper() + canon[1:]
                out.append(canon)
            pos = m.end()
        out.append(translated[pos:])
        if len(seen) != len(canonicals):
            ok = False
        result = "".join(out)
        if not ok:
            result = _DOUBLE_SPACE.sub(" ", result).strip()
        return result, ok
