"""Cliente da API nativa do Ollama (/api/chat).

O endpoint compatível com OpenAI (/v1) ignora `num_ctx` (tudo roda com o contexto padrão e prompts
maiores são truncados em silêncio) e não desliga o raciocínio dos modelos "thinking". A API nativa
aceita ambos por requisição e faz saída estruturada com `format` (schema JSON), inclusive em modelos
sem suporte a tools, como o TranslateGemma.
"""

import logging

import httpx
from pydantic import BaseModel, ValidationError

from translaterany.llm.client import LLMConfigError, LLMOutputError, LLMResponse, LLMTransientError, Usage

logger = logging.getLogger(__name__)

_ATTEMPTS = 2  # uma nova tentativa quando o JSON não valida
_SATURATION_MARGIN = 32  # tokens de folga antes de considerar o contexto saturado


def ollama_root(base_url: str) -> str:
    """URL do provedor no config (ex.: http://localhost:11434/v1) -> raiz da API nativa."""
    root = base_url.rstrip("/")
    return root[: -len("/v1")] if root.endswith("/v1") else root


class OllamaNativeClient:
    def __init__(self, base_url: str, http: httpx.Client | None = None, timeout: float = 900.0) -> None:
        self.base_url = ollama_root(base_url)
        self._http = http or httpx.Client(base_url=self.base_url, timeout=timeout)

    def chat[T: BaseModel](
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        output_type: type[T],
        num_ctx: int,
        temperature: float,
        think: bool,
    ) -> LLMResponse[T]:
        body = {
            "model": model,
            "stream": False,
            "think": think,
            "format": output_type.model_json_schema(),
            "options": {"num_ctx": num_ctx, "temperature": temperature},
            "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}],
        }
        error: Exception | None = None
        for _ in range(_ATTEMPTS):
            data = self._post(body, model)
            prompt_tokens = int(data.get("prompt_eval_count") or 0)
            output_tokens = int(data.get("eval_count") or 0)
            if data.get("done_reason") == "length":
                raise LLMOutputError(
                    f"resposta de {model} cortada pelo limite de contexto (num_ctx={num_ctx}); "
                    "aumente num_ctx do modelo em [llm.models] ou reduza o prompt"
                )
            if prompt_tokens + output_tokens >= num_ctx - _SATURATION_MARGIN:
                logger.warning(
                    "contexto de %s saturado (%d de %d tokens): o prompt pode ter sido truncado — aumente num_ctx",
                    model,
                    prompt_tokens + output_tokens,
                    num_ctx,
                )
            content = (data.get("message") or {}).get("content") or ""
            try:
                output = output_type.model_validate_json(content)
            except ValidationError as exc:
                error = exc
                continue
            return LLMResponse(output=output, model_id=model, usage=Usage(prompt_tokens, output_tokens))
        raise LLMOutputError(f"saída estruturada inválida de {model} após {_ATTEMPTS} tentativas: {error}")

    def _post(self, body: dict, model: str) -> dict:
        try:
            response = self._http.post("/api/chat", json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise LLMTransientError(f"erro de conexão com o Ollama ({model}): {exc}") from exc
        if response.status_code >= 500:
            raise LLMTransientError(f"Ollama respondeu {response.status_code} para {model}: {_error_text(response)}")
        if response.status_code >= 400:
            raise LLMConfigError(f"Ollama recusou a requisição para {model}: {_error_text(response)}")
        return response.json()


def _error_text(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error") or response.text)
    except ValueError:
        return response.text
