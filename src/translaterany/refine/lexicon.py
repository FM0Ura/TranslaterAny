"""Padrões de PT-BR duro/literal que indicam candidatas à coloquialidade. Amplie aqui."""

import re

FORMAL_CONNECTIVE = re.compile(r"\b(?:no entanto|entretanto|contudo|todavia|a fim de|portanto)\b", re.IGNORECASE)
ENCLISIS = re.compile(r"\b\w+[aeiouáéêíóô]-(?:lo|la|los|las|se|me|te|nos)\b|^\s*\w+-se\b", re.IGNORECASE)
REDUNDANT_SUBJECT = re.compile(r"^\s*eu (?:estou|sou|vou|tenho)\b", re.IGNORECASE)
ARCHAIC_PRONOUN = re.compile(r"\b(?:tu|vós|convosco)\b", re.IGNORECASE)
TOO_LONG_RATIO = 1.3
TOO_LONG_MIN_CHARS = 10
