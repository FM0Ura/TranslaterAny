import pytest
from pydantic import BaseModel

from translaterany.llm import FakeLLM, LLMConfigError, LLMRequest, LLMTransientError


class Answer(BaseModel):
    value: str


class Other(BaseModel):
    n: int


def _req(prompt: str = "p") -> LLMRequest[Answer]:
    return LLMRequest(model="leve", instructions="inst", prompt=prompt, output_type=Answer, tag="t")


def test_unconfigured_raises_config_error() -> None:
    with pytest.raises(LLMConfigError):
        FakeLLM().generate(_req())


def test_scripted_responses_in_order_and_calls_recorded() -> None:
    llm = FakeLLM([Answer(value="a"), Answer(value="b")])
    assert llm.generate(_req("1")).output.value == "a"
    response = llm.generate(_req("2"))
    assert response.output.value == "b"
    assert response.model_id == "fake:leve"
    assert response.usage.input_tokens > 0
    assert [c.prompt for c in llm.calls] == ["1", "2"]


def test_scripted_exception_is_raised_then_continues() -> None:
    llm = FakeLLM([LLMTransientError("timeout"), Answer(value="ok")])
    with pytest.raises(LLMTransientError):
        llm.generate(_req())
    assert llm.generate(_req()).output.value == "ok"


def test_script_exhausted() -> None:
    llm = FakeLLM([])
    with pytest.raises(LLMConfigError, match="esgotado"):
        llm.generate(_req())


def test_function_script() -> None:
    llm = FakeLLM(lambda req: Answer(value=req.prompt.upper()))
    assert llm.generate(_req("oi")).output.value == "OI"


def test_wrong_output_type_is_rejected() -> None:
    llm = FakeLLM([Other(n=1)])
    with pytest.raises(TypeError):
        llm.generate(_req())


def test_generic_output_type_from_responses() -> None:
    class GenericModel(BaseModel):
        msg: str = "default"

    llm = FakeLLM(responses={})
    req = LLMRequest(model="test", instructions="", prompt="", output_type=GenericModel)
    resp = llm.generate(req)
    assert isinstance(resp.output, GenericModel)
    assert resp.output.msg == "default"


def test_script_exhaustion_falls_back_to_responses() -> None:
    from translaterany.subtitles.translator import TranslationBatch

    llm = FakeLLM(
        script=[Answer(value="custom")],
        responses={"hello": "olá"},
    )
    # Primeiro pedido consome da fila de script
    assert llm.generate(_req("req1")).output.value == "custom"
    # Segundo pedido cai em responses
    tr_req = LLMRequest(model="test", instructions="", prompt="[0] hello", output_type=TranslationBatch)
    tr_resp = llm.generate(tr_req)
    assert tr_resp.output.items[0].text == "olá"
