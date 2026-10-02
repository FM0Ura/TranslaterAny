"""Algoritmo de coerência de tratamento (você/tu/senhor) e gênero entre personagens (M7)."""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_TU_RE = re.compile(r"\b(tu|te|ti|teu|teus|tua|tuas)\b|\b\w+(?:ste|stes)\b", re.IGNORECASE)
_VOCE_RE = re.compile(r"\b(você|vocês|cê|cês|seu|seus|sua|suas)\b", re.IGNORECASE)
_SENHOR_RE = re.compile(r"\b(?:o senhor|a senhora|os senhores|as senhoras)\b", re.IGNORECASE)

_MASC_PREDICATES = r"(?:cansado|preocupado|pronto|grato|obrigado|sozinho|animado|chateado|perdido|seguro|surpreso|confuso|satisfeito|vazio|furioso|bravo|louco)"
_FEM_PREDICATES = r"(?:cansada|preocupada|pronta|grata|obrigada|sozinha|animada|chateada|perdida|segura|surpresa|confusa|satisfeita|vazia|furiosa|brava|louca)"

_FEM_SPEAKER_MASC_ERROR = re.compile(
    rf"\b(?:eu\s+)?(?:estou|tô|fiquei|sou|fui|me\s+sinto|me\s+deixa(?:ndo)?)\s+{_MASC_PREDICATES}\b", re.IGNORECASE
)
_MASC_SPEAKER_FEM_ERROR = re.compile(
    rf"\b(?:eu\s+)?(?:estou|tô|fiquei|sou|fui|me\s+sinto|me\s+deixa(?:ndo)?)\s+{_FEM_PREDICATES}\b", re.IGNORECASE
)


@dataclass
class PairTreatment:
    canonical_pronoun: str
    divergent_ids: list[str] = field(default_factory=list)
    divergent_reasons: dict[str, list[str]] = field(default_factory=dict)


def scan_treatment_consistency(
    lines: Iterable[dict[str, Any] | Any],
    character_gender: Mapping[str, str] | None = None,
) -> dict[tuple[str, str], PairTreatment]:
    """Identifica falas divergentes do padrão pronominal e de gênero de cada par."""
    gender_map = {k: v.lower() for k, v in (character_gender or {}).items()}
    spk_gender_map = {k.lower(): v.lower() for k, v in (character_gender or {}).items()}

    pair_lines: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in lines:
        d = item if isinstance(item, dict) else item.__dict__
        spk = d.get("speaker") or "Unknown"
        lis = d.get("listener") or "Unknown"
        conf = d.get("confidence") or "low"
        if spk == "Unknown" or lis == "Unknown" or conf != "high":
            continue
        pair_lines[(spk, lis)].append(d)

    result: dict[tuple[str, str], PairTreatment] = {}
    for pair, group in pair_lines.items():
        spk, lis = pair
        tu_count = 0
        voce_count = 0
        senhor_count = 0
        line_pronoun: dict[str, str] = {}
        gender_mismatches: dict[str, list[str]] = defaultdict(list)

        for line in group:
            lid = line["id"]
            text = line.get("text", "")

            # Pronome usado
            has_tu = bool(_TU_RE.search(text))
            has_voce = bool(_VOCE_RE.search(text))
            has_senhor = bool(_SENHOR_RE.search(text))

            if has_tu and not has_voce:
                tu_count += 1
                line_pronoun[lid] = "tu"
            elif has_voce and not has_tu:
                voce_count += 1
                line_pronoun[lid] = "voce"
            elif has_senhor:
                senhor_count += 1
                line_pronoun[lid] = "senhor"

            # Gênero do falante
            spk_gen = spk_gender_map.get(spk.lower())
            if spk_gen in ("female", "f"):
                if _FEM_SPEAKER_MASC_ERROR.search(text):
                    gender_mismatches[lid].append("gênero masculino usado por falante feminina")
            elif spk_gen in ("male", "m"):
                if _MASC_SPEAKER_FEM_ERROR.search(text):
                    gender_mismatches[lid].append("gênero feminino usado por falante masculino")

            # Artigos com personagens ou alcunhas mencionados na fala
            for name, gen in gender_map.items():
                if len(name) < 3:
                    continue
                if gen in ("female", "f"):
                    if re.search(rf"\b(?:o|do|no|pelo|ao|nosso)\s+{re.escape(name)}\b", text, re.IGNORECASE):
                        gender_mismatches[lid].append(f"artigo masculino usado para personagem feminina '{name}'")
                elif gen in ("male", "m"):
                    if re.search(rf"\b(?:a|da|na|pela|à|nossa)\s+{re.escape(name)}\b", text, re.IGNORECASE):
                        gender_mismatches[lid].append(f"artigo feminino usado para personagem masculino '{name}'")

        # Define maioria
        if tu_count > voce_count and tu_count > senhor_count:
            canonical = "tu"
        elif senhor_count > voce_count and senhor_count > tu_count:
            canonical = "senhor"
        else:
            canonical = "voce"

        divergent_ids: list[str] = []
        divergent_reasons: dict[str, list[str]] = {}

        for line in group:
            lid = line["id"]
            reasons: list[str] = []
            used_pronoun = line_pronoun.get(lid)
            if used_pronoun and used_pronoun != canonical:
                reasons.append(f"usou '{used_pronoun}' em vez de '{canonical}'")
            if lid in gender_mismatches:
                reasons.extend(gender_mismatches[lid])

            if reasons:
                divergent_ids.append(lid)
                divergent_reasons[lid] = reasons

        if divergent_ids:
            result[pair] = PairTreatment(
                canonical_pronoun=canonical,
                divergent_ids=divergent_ids,
                divergent_reasons=divergent_reasons,
            )

    return result
