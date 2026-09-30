"""Medidor de uso da IA: envolve um LLMClient e conta chamadas, tokens, custo e erros."""

from pydantic import BaseModel, Field

from translaterany.llm.client import (
    LLMClient,
    LLMConfigError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
)
from translaterany.llm.pricing import PriceFn

_ERROR_KINDS: tuple[tuple[type[Exception], str], ...] = (
    (LLMTransientError, "transient"),
    (LLMOutputError, "output"),
    (LLMRefusalError, "refusal"),
    (LLMConfigError, "config"),
)


class ModelStats(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: ModelStats) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cost_usd += other.cost_usd


class LLMStats(BaseModel):
    calls: int = 0
    errors: dict[str, int] = Field(default_factory=dict)
    by_model: dict[str, ModelStats] = Field(default_factory=dict)

    @property
    def input_tokens(self) -> int:
        return sum(m.input_tokens for m in self.by_model.values())

    @property
    def output_tokens(self) -> int:
        return sum(m.output_tokens for m in self.by_model.values())

    @property
    def cost_usd(self) -> float:
        return sum(m.cost_usd for m in self.by_model.values())

    def add(self, other: LLMStats) -> None:
        self.calls += other.calls
        for kind, n in other.errors.items():
            self.errors[kind] = self.errors.get(kind, 0) + n
        for model_id, stats in other.by_model.items():
            self.by_model.setdefault(model_id, ModelStats()).add(stats)


def _error_kind(exc: Exception) -> str:
    return next((kind for cls, kind in _ERROR_KINDS if isinstance(exc, cls)), "other")


class MeteredLLM:
    """Um por (etapa, unidade). Relança os erros: o comportamento das etapas não muda."""

    def __init__(self, inner: LLMClient, prices: PriceFn | None = None) -> None:
        self.inner = inner
        self.prices = prices
        self.stats = LLMStats()

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        self.stats.calls += 1
        try:
            response = self.inner.generate(request)
        except Exception as exc:
            kind = _error_kind(exc)
            self.stats.errors[kind] = self.stats.errors.get(kind, 0) + 1
            raise
        in_price, out_price = self.prices(request.model) if self.prices else (0.0, 0.0)
        usage = response.usage
        model = self.stats.by_model.setdefault(response.model_id, ModelStats())
        model.add(
            ModelStats(
                calls=1,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cost_usd=(usage.input_tokens * in_price + usage.output_tokens * out_price) / 1_000_000,
            )
        )
        return response
