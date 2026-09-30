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
PT_PT_WORDS = re.compile(
    r"\b(?:autocarro|comboio|telemóvel|equipa|facto|ecrã|rapariga|casa de banho|pequeno-almoço)\b", re.IGNORECASE
)
PT_PT_PROGRESSIVE = re.compile(
    r"\b(?:estou|estás|está|estamos|estão|estava|estavam) a \w+(?:ar|er|ir)\b", re.IGNORECASE
)
SPANISH = re.compile(r"[¿¡ñÑ]|\b(?:pero|muy|también|usted|gracias|hola)\b", re.IGNORECASE)
PT_PROFANITY = re.compile(
    r"\b(?:merda|porra|caralho|puta|puto|foda|foder|fodido|fodida|cacete|desgraça|desgraçado|desgraçada|"
    r"arrombado|arrombada|babaca|idiota|imbecil|otário|otária|vadia|cuzão)\b",
    re.IGNORECASE,
)
EN_PROFANITY = re.compile(
    r"\b(?:shit|fuck\w*|damn\w*|bitch\w*|bastard\w*|ass|asshole|crap|idiot\w*|moron\w*|jerk\w*|hell|"
    r"dumbass|screw\w*|piss\w*|dick\w*|stupid|fool\w*|dumb\w*|loser\w*|pervert\w*)\b",
    re.IGNORECASE,
)
