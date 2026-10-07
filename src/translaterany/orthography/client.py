"""Cliente HTTP para o serviço local do LanguageTool com filtros de regras e isenções (M7)."""

import logging
import unicodedata
from collections.abc import Set
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {"TYPOS", "CASING", "GRAMMAR"}
BLOCKED_CATEGORIES = {"STYLE", "COLLOQUIALISMS"}


def _strip_accents(word: str) -> str:
    """Remove diacríticos (preservando a caixa), para detectar correções que só mudam acentuação."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


class LanguageToolClient:
    """Cliente HTTP com degradação graciosa para o LanguageTool."""

    def __init__(
        self,
        url: str = "http://localhost:8010/v2/check",
        timeout_s: float = 5.0,
        language: str = "pt-BR",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self.language = language
        self.transport = transport
        self.is_offline = False

    def correct_text(self, text: str, exemptions: Set[str] | None = None) -> tuple[str, int]:
        """Envia o texto ao LanguageTool e aplica correções seguras em ordem inversa."""
        if not text.strip() or self.is_offline:
            return text, 0

        clean_exemptions = {e.strip().lower() for e in (exemptions or set()) if e}

        try:
            with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                resp = client.post(
                    self.url,
                    data={"text": text, "language": self.language},
                )
                if resp.status_code != 200:
                    logger.warning("LanguageTool retornou status %s", resp.status_code)
                    return text, 0
                data = resp.json()
        except Exception as exc:
            logger.warning("LanguageTool indisponível (%s); degradando com elegância.", exc)
            self.is_offline = True
            return text, 0

        matches: list[dict[str, Any]] = data.get("matches", [])
        if not matches:
            return text, 0

        # Ordena de trás para frente para não invalidar offsets
        matches.sort(key=lambda m: m.get("offset", 0), reverse=True)

        applied = 0
        result = text
        for match in matches:
            cat = match.get("rule", {}).get("category", {}).get("id", "")
            if cat in BLOCKED_CATEGORIES or (cat and cat not in ALLOWED_CATEGORIES):
                continue

            offset = match.get("offset", 0)
            length = match.get("length", 0)
            original = result[offset : offset + length]

            cleaned_orig = original.strip("-,.?!:; ").lower()
            if (
                original.lower() in clean_exemptions
                or cleaned_orig in clean_exemptions
                or any(part in clean_exemptions for part in cleaned_orig.split("-") if part)
            ):
                continue

            # Salvaguarda: Não substituir palavras capitalizadas (nomes próprios) por sugestões de TYPOS
            # quando não estão no início de uma frase/fala.
            is_title = bool(original and original[0].isupper())
            is_sentence_start = offset == 0 or (
                offset > 0
                and text[:offset].rstrip().endswith((".", "!", "?", "…", "—", '"', "“", "”", "¿", "¡", "-", ":"))
            )
            if cat == "TYPOS" and is_title and not is_sentence_start:
                continue

            replacements = match.get("replacements", [])
            if not replacements:
                continue

            sub = replacements[0].get("value")
            if not sub or sub == original:
                continue

            # Salvaguarda: só aceita correções de acentuação. A primeira sugestão do LanguageTool para
            # estrangeirismos, onomatopeias e coloquialismos (tsundere->sugere, nyan->miam, Putz->Pubs) ou
            # reescritas de gênero/caixa em fragmentos de fala corrompem a legenda.
            if _strip_accents(sub) != _strip_accents(original):
                continue

            result = result[:offset] + sub + result[offset + length :]
            applied += 1

        return result, applied
