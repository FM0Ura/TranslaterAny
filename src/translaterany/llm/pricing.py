"""Tabela de preços por apelido de modelo (USD por milhão de tokens)."""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # evita ciclo: config -> pipeline -> manifest -> llm.metered -> pricing
    from translaterany.config.model import LLMConfig

type PriceFn = Callable[[str], tuple[float, float]]


def price_lookup(cfg: LLMConfig) -> PriceFn:
    """Resolve o apelido como o PydanticAIClient: papel do perfil ativo (translate/review) ou chave de modelo."""

    def prices(alias: str) -> tuple[float, float]:
        profile = cfg.profiles.get(cfg.profile)
        key = alias
        if profile is not None and alias in ("translate", "review"):
            key = getattr(profile, alias)
        model = cfg.models.get(key)
        if model is None:
            return (0.0, 0.0)
        return (model.input_price_per_mtok, model.output_price_per_mtok)

    return prices
