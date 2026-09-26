"""LLM falso e roteirizável, para testes sem IA real."""

import re
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

    def __init__(
        self,
        script: Iterable[Scripted] | ScriptFn | None = None,
        *,
        responses: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[LLMRequest[Any]] = []
        self._fn: ScriptFn | None = None
        self._queue: deque[Scripted] | None = None
        self._responses: dict[str, str] | None = responses
        if callable(script):
            self._fn = script
        elif script is not None:
            self._queue = deque(script)

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        self.calls.append(request)
        if self._fn is not None:
            item = self._fn(request)
        elif self._queue:
            item = self._queue.popleft()
        elif self._responses is not None:
            from translaterany.subtitles.translator import TranslationBatch, TranslationItem

            if issubclass(request.output_type, TranslationBatch) or request.output_type is TranslationBatch:
                items: list[TranslationItem] = []
                for line in request.prompt.splitlines():
                    m = re.match(r"^\[([^\]]+)\]\s*(.*)$", line.strip())
                    if m:
                        line_id, text = m.group(1), m.group(2)
                        if line_id.startswith("CTX-"):
                            continue
                        tr = self._responses.get(text)
                        if tr is None:
                            for k, v in self._responses.items():
                                if k in text:
                                    tr = v
                                    break
                        items.append(TranslationItem(id=line_id, text=tr if tr is not None else text))
                item = TranslationBatch(items=items)
            else:
                try:
                    item = request.output_type()
                except Exception:
                    try:
                        item = request.output_type.model_validate({})
                    except Exception:
                        item = request.output_type.model_construct()
        elif self._queue is not None and not self._queue:
            raise LLMConfigError("roteiro do FakeLLM esgotado")
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
