"""MeteredLLM e StageMetrics (M5)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from translaterany.llm.client import LLMConfigError, LLMOutputError, LLMRefusalError, LLMRequest, LLMTransientError
from translaterany.llm.fake import FakeLLM
from translaterany.llm.metered import LLMStats, MeteredLLM, ModelStats
from translaterany.pipeline.stage_metrics import StageMetrics, count


class Out(BaseModel):
    text: str = "ok"


def req(model: str = "translate") -> LLMRequest[Out]:
    return LLMRequest(model=model, instructions="x" * 400, prompt="y" * 400, output_type=Out)


def test_counts_tokens_and_cost_by_model() -> None:
    metered = MeteredLLM(FakeLLM([Out(), Out()]), prices=lambda alias: (2.0, 8.0))
    metered.generate(req())
    metered.generate(req())
    stats = metered.stats
    assert stats.calls == 2
    model = stats.by_model["fake:translate"]
    assert model.calls == 2
    assert model.input_tokens == 400  # FakeLLM: (400 + 400) // 4 por chamada
    assert stats.input_tokens == 400
    expected = (model.input_tokens * 2.0 + model.output_tokens * 8.0) / 1_000_000
    assert stats.cost_usd == pytest.approx(expected)


@pytest.mark.parametrize(
    ("error", "kind"),
    [(LLMTransientError("t"), "transient"), (LLMOutputError("o"), "output"), (LLMRefusalError("r"), "refusal"),
     (RuntimeError("x"), "other")],
)  # fmt: skip
def test_errors_are_counted_and_reraised(error: Exception, kind: str) -> None:
    metered = MeteredLLM(FakeLLM([error]))
    with pytest.raises(type(error)):
        metered.generate(req())
    assert metered.stats.calls == 1
    assert metered.stats.errors == {kind: 1}
    assert metered.stats.by_model == {}


def test_config_error_and_no_prices() -> None:
    metered = MeteredLLM(FakeLLM())  # sem provedor: LLMConfigError
    with pytest.raises(LLMConfigError):
        metered.generate(req())
    assert metered.stats.errors == {"config": 1}
    ok = MeteredLLM(FakeLLM([Out()]))
    ok.generate(req("desconhecido"))
    assert ok.stats.cost_usd == 0.0


def test_stats_add_merges() -> None:
    a = LLMStats(calls=1, errors={"output": 1}, by_model={"m": ModelStats(calls=1, input_tokens=10, cost_usd=0.5)})
    b = LLMStats(calls=2, errors={"output": 2}, by_model={"m": ModelStats(calls=2, input_tokens=5, cost_usd=0.25)})
    a.add(b)
    assert a.calls == 3 and a.errors == {"output": 3}
    assert a.by_model["m"].input_tokens == 15 and a.cost_usd == pytest.approx(0.75)


def test_stage_metrics_count_and_helper() -> None:
    m = StageMetrics()
    m.count("lines", 3)
    m.count("lines")
    assert m.counters == {"lines": 4}
    ctx = SimpleNamespace(metrics=m)
    count(ctx, "fallback_original")
    assert m.counters["fallback_original"] == 1
    count(SimpleNamespace(), "ignored")  # contexto falso sem metrics: não quebra
