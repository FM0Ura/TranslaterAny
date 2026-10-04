"""Catálogo canônico e resolução universal de idiomas."""

import re
import unicodedata
from translaterany.languages.models import LanguageInfo

_NON_ALPHANUM = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """Normaliza texto removendo acentos, pontuações e caixa alta."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return _NON_ALPHANUM.sub("", ascii_text)


class LanguageRegistry:
    """Catálogo e resolvedor de idiomas."""

    # Catálogo canônico dos principais idiomas
    _CATALOG: dict[str, LanguageInfo] = {
        "pt-BR": LanguageInfo(
            code="pt-BR",
            iso639_1="pt",
            iso639_2="por",
            name_pt="português do Brasil",
            name_en="Brazilian Portuguese",
            name_native="Português (Brasil)",
            languagetool_code="pt-BR",
        ),
        "en": LanguageInfo(
            code="en",
            iso639_1="en",
            iso639_2="eng",
            name_pt="inglês",
            name_en="English",
            name_native="English",
            languagetool_code="en-US",
        ),
        "es": LanguageInfo(
            code="es",
            iso639_1="es",
            iso639_2="spa",
            name_pt="espanhol",
            name_en="Spanish",
            name_native="Español",
            languagetool_code="es",
        ),
        "ja": LanguageInfo(
            code="ja",
            iso639_1="ja",
            iso639_2="jpn",
            name_pt="japonês",
            name_en="Japanese",
            name_native="日本語",
            languagetool_code="ja",
        ),
        "fr": LanguageInfo(
            code="fr",
            iso639_1="fr",
            iso639_2="fre",
            name_pt="francês",
            name_en="French",
            name_native="Français",
            languagetool_code="fr",
        ),
        "de": LanguageInfo(
            code="de",
            iso639_1="de",
            iso639_2="ger",
            name_pt="alemão",
            name_en="German",
            name_native="Deutsch",
            languagetool_code="de-DE",
        ),
        "it": LanguageInfo(
            code="it",
            iso639_1="it",
            iso639_2="ita",
            name_pt="italiano",
            name_en="Italian",
            name_native="Italiano",
            languagetool_code="it",
        ),
        "zh": LanguageInfo(
            code="zh",
            iso639_1="zh",
            iso639_2="chi",
            name_pt="chinês",
            name_en="Chinese",
            name_native="中文",
            languagetool_code="zh-CN",
        ),
        "ko": LanguageInfo(
            code="ko",
            iso639_1="ko",
            iso639_2="kor",
            name_pt="coreano",
            name_en="Korean",
            name_native="한국어",
            languagetool_code="ko",
        ),
        "ru": LanguageInfo(
            code="ru",
            iso639_1="ru",
            iso639_2="rus",
            name_pt="russo",
            name_en="Russian",
            name_native="Русский",
            languagetool_code="ru-RU",
        ),
    }

    # Mapa de aliases flexíveis -> chave canônica do catálogo
    _ALIASES: dict[str, str] = {
        # Português
        "pt": "pt-BR",
        "ptbr": "pt-BR",
        "por": "pt-BR",
        "portugues": "pt-BR",
        "portuguesdobrasil": "pt-BR",
        "brazilianportuguese": "pt-BR",
        # Inglês
        "en": "en",
        "eng": "en",
        "enus": "en",
        "engb": "en",
        "english": "en",
        "ingles": "en",
        # Espanhol
        "es": "es",
        "spa": "es",
        "eses": "es",
        "es419": "es",
        "spanish": "es",
        "espanhol": "es",
        "castellano": "es",
        # Japonês
        "ja": "ja",
        "jp": "ja",
        "jpn": "ja",
        "japon": "ja",
        "japanese": "ja",
        "japones": "ja",
        "nihongo": "ja",
        # Francês
        "fr": "fr",
        "fra": "fr",
        "fre": "fr",
        "french": "fr",
        "frances": "fr",
        # Alemão
        "de": "de",
        "ger": "deu",
        "deu": "de",
        "german": "de",
        "alemao": "de",
        # Italiano
        "it": "it",
        "ita": "it",
        "italian": "it",
        "italiano": "it",
        # Chinês
        "zh": "zh",
        "chi": "zh",
        "zho": "zh",
        "chinese": "zh",
        "chines": "zh",
        # Coreano
        "ko": "ko",
        "kor": "ko",
        "korean": "ko",
        "coreano": "ko",
        # Russo
        "ru": "ru",
        "rus": "ru",
        "russian": "ru",
        "russo": "ru",
    }

    @classmethod
    def resolve(cls, query: str) -> LanguageInfo:
        """Resolve uma string de código ou alias para uma LanguageInfo canônica."""
        if not query or not query.strip():
            return cls._CATALOG["en"]

        raw = query.strip()
        # 1. Correspondência direta exata no catálogo
        if raw in cls._CATALOG:
            return cls._CATALOG[raw]

        # 2. Busca por slug normalizado nos aliases
        slug_key = _slug(raw)
        if slug_key in cls._ALIASES:
            canonical_key = cls._ALIASES[slug_key]
            return cls._CATALOG[canonical_key]

        # 3. Busca por correspondência no código ou ISOs do catálogo
        for item in cls._CATALOG.values():
            if slug_key in (_slug(item.code), _slug(item.iso639_1), _slug(item.iso639_2)):
                return item

        # 4. Fallback universal resiliente para código não catalogado (ex.: "sw", "nl", "pl")
        base_code = raw.replace("_", "-")
        iso1 = base_code.split("-")[0].lower()
        return LanguageInfo(
            code=base_code,
            iso639_1=iso1,
            iso639_2=iso1,
            name_pt=raw,
            name_en=raw,
            name_native=raw,
            languagetool_code=base_code,
        )

    @classmethod
    def matches(cls, track_lang: str, target: LanguageInfo) -> bool:
        """Verifica se o idioma de uma faixa no MKV corresponde ao idioma alvo."""
        if not track_lang:
            return False

        track_slug = _slug(track_lang)
        if not track_slug:
            return False

        # Verifica se o código da faixa bate com o target diretamente
        if track_slug in (_slug(target.code), _slug(target.iso639_1), _slug(target.iso639_2)):
            return True

        # Verifica se resolvendo a faixa chega-se ao mesmo target
        resolved = cls.resolve(track_lang)
        return resolved.code == target.code
