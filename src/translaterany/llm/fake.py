"""LLM falso e roteirizável, para testes sem IA real."""

from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel

from translaterany.llm.client import LLMConfigError, LLMRequest, LLMResponse, Usage

type Scripted = BaseModel | Exception
type ScriptFn = Callable[[LLMRequest[Any]], Scripted]


class FakeLLM:
    """Devolve respostas roteirizadas, na ordem, ou calculadas por uma função.

    - `FakeLLM()`: nenhum provedor configurado; qualquer chamada lança LLMConfigError.
    - `FakeLLM([resp1, erro, resp2])`: devolve/lança cada item em ordem.
    - `FakeLLM(lambda req: ...)`: calcula a resposta a partir da requisição.
    """

    def __init__(self, script: Iterable[Scripted] | ScriptFn | None = None) -> None:
        self.calls: list[LLMRequest[Any]] = []
        self._fn: ScriptFn | None = None
        self._queue: deque[Scripted] | None = None
        if callable(script):
            self._fn = script
        elif script is not None:
            self._queue = deque(script)

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        self.calls.append(request)
        if self._fn is not None:
            item = self._fn(request)
        elif self._queue is not None:
            if not self._queue:
                raise LLMConfigError("roteiro do FakeLLM esgotado")
            item = self._queue.popleft()
        else:
            raise LLMConfigError("nenhum provedor de IA configurado")

        if isinstance(item, Exception):
            raise item
        if not isinstance(item, request.output_type):
            raise TypeError(f"FakeLLM: resposta {type(item).__name__} não é {request.output_type.__name__}")
        usage = Usage(
            input_tokens=(len(request.instructions) + len(request.prompt)) // 4,
            output_tokens=len(item.model_dump_json()) // 4,
        )
        return LLMResponse(output=item, model_id=f"fake:{request.model}", usage=usage)
