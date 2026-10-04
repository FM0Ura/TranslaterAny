"""Modelos de dados para a camada universal de idiomas."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageInfo:
    """Representação canônica de um idioma."""

    code: str  # Código canônico IETF BCP-47 (ex.: "pt-BR", "en", "es", "ja")
    iso639_1: str  # Código ISO 639-1 de 2 letras (ex.: "pt", "en", "es", "ja")
    iso639_2: str  # Código ISO 639-2 de 3 letras para MKV (ex.: "por", "eng", "spa", "jpn")
    name_pt: str  # Nome legível em português para uso nos prompts da LLM (ex.: "português do Brasil", "japonês")
    name_en: str  # Nome legível em inglês (ex.: "Brazilian Portuguese", "Japanese")
    name_native: str  # Nome na língua nativa (ex.: "Português", "日本語", "Español")
    languagetool_code: str  # Código compatível com o servidor LanguageTool (ex.: "pt-BR", "en-US", "es")


@dataclass
class TreatmentReport:
    """Relatório de inconsistências de tratamento ou flexão de gênero."""

    divergent_reasons: dict[str, list[str]] = field(default_factory=dict)
