"""Listas de palavras e padrões usados pelas checagens. Amplie aqui, não nas regras."""

import re

# Palavras funcionais inglesas que não existem como palavra em PT-BR ("a", "do", "no", "me", "se" ficam de fora).
EN_FUNCTION_WORDS = frozenset(
    {
        "the", "and", "you", "your", "is", "are", "was", "were", "to", "of", "what", "that", "this", "it",
        "i", "i'm", "don't", "it's", "with", "for", "have", "be", "will", "can", "my", "we", "they", "he",
        "she", "not", "just", "but", "there", "here", "all", "know", "why", "where", "when", "how",
    }
)  # fmt: skip

EN_NEGATION = re.compile(
    r"\b(?:not|never|no|nobody|nothing|none|neither|nor|without|nowhere|cannot)\b|n't\b", re.IGNORECASE
)
PT_NEGATION = re.compile(r"\b(?:não|nunca|nem|nada|ninguém|nenhum|nenhuma|jamais|sem)\b", re.IGNORECASE)
DIGITS = re.compile(r"\d+")
