import asyncio
import concurrent.futures
import os
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ContentFilterError, UnexpectedModelBehavior

from translaterany.llm.client import (
    LLMClient,
    LLMConfigError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
    Usage,
)

if TYPE_CHECKING:
    from translaterany.config.model import LLMConfig

network_errors = [httpx.ConnectError, httpx.TimeoutException]
try:
    import openai

    network_errors.extend([openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError])
except ImportError:
    pass

NETWORK_ERRORS = tuple(set(network_errors))

try:
    from pydantic_ai.models.openai import OpenAIModel  # type: ignore[attr-defined]
except ImportError:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    class OpenAIModel(OpenAIChatModel):  # type: ignore[no-redef]
        def __init__(
            self,
            model_name: str,
            base_url: str | None = None,
            api_key: str | None = None,
            **kwargs: Any,
        ) -> None:
            provider = OpenAIProvider(base_url=base_url, api_key=api_key)
            super().__init__(model_name=model_name, provider=provider, **kwargs)


class PydanticAIClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config

    def _resolve_model(self, model_alias: str) -> tuple[str, str | None, str | None, dict[str, Any]]:
        # Resolve se model_alias for o nome direto ou tarefa do perfil ativo
        active_profile = self.config.profiles.get(self.config.profile)
        if active_profile and hasattr(active_profile, model_alias):
            resolved = getattr(active_profile, model_alias)
            if isinstance(resolved, str):
                model_alias = resolved

        if model_alias not in self.config.models:
            raise LLMConfigError(f"Modelo '{model_alias}' não configurado em [llm.models].")

        model_cfg = self.config.models[model_alias]
        provider_cfg = self.config.providers.get(model_cfg.provider)
        if not provider_cfg:
            raise LLMConfigError(f"Provedor '{model_cfg.provider}' não configurado em [llm.providers].")

        # Base URL resolution
        if provider_cfg.base_url:
            base_url = provider_cfg.base_url
        elif model_cfg.provider == "ollama":
            base_url = "http://localhost:11434/v1"
        else:
            base_url = None

        # API key resolution
        api_key = provider_cfg.api_key
        if not api_key:
            if model_cfg.provider == "openai":
                api_key = os.environ.get("OPENAI_API_KEY")
            elif model_cfg.provider == "gemini":
                api_key = os.environ.get("GEMINI_API_KEY")
            elif model_cfg.provider == "ollama":
                api_key = "ollama"

        extra_args: dict[str, Any] = {"temperature": model_cfg.temperature}
        if model_cfg.num_ctx:
            extra_args["extra_body"] = {"num_ctx": model_cfg.num_ctx}

        return model_cfg.model, base_url, api_key, extra_args

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        model_name, base_url, api_key, extra_args = self._resolve_model(request.model)

        if request.temperature is not None:
            extra_args["temperature"] = request.temperature

        model = OpenAIModel(
            model_name=model_name,
            base_url=base_url,
            api_key=api_key or "ollama",
        )

        try:
            agent = Agent(
                model=model,
                system_prompt=request.instructions,
                output_type=request.output_type,
                model_settings=extra_args,
            )
        except TypeError:
            agent = Agent(  # type: ignore[call-arg]
                model=model,
                system_prompt=request.instructions,
                result_type=request.output_type,
            )

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    result = executor.submit(lambda: asyncio.run(agent.run(request.prompt))).result()
            else:
                result = asyncio.run(agent.run(request.prompt))
        except NETWORK_ERRORS as exc:
            raise LLMTransientError(f"Erro de conexão com o modelo ({model_name}): {exc}") from exc
        except Exception as exc:
            if isinstance(exc, ContentFilterError):
                raise LLMRefusalError(f"Requisição recusada pelo modelo: {exc}") from exc
            if isinstance(exc, (UnexpectedModelBehavior, ValidationError)):
                raise LLMOutputError(f"Falha de validação da saída estruturada: {exc}") from exc

            msg = str(exc).lower()
            if "safety" in msg or "refus" in msg:
                raise LLMRefusalError(f"Requisição recusada pelo modelo: {exc}") from exc
            if "validation" in msg or "json" in msg:
                raise LLMOutputError(f"Falha de validação da saída estruturada: {exc}") from exc
            raise

        raw_usage = result.usage() if callable(getattr(result, "usage", None)) else getattr(result, "usage", None)
        usage = Usage(
            input_tokens=getattr(raw_usage, "request_tokens", 0) or getattr(raw_usage, "input_tokens", 0) or 0,
            output_tokens=getattr(raw_usage, "response_tokens", 0) or getattr(raw_usage, "output_tokens", 0) or 0,
        )

        return LLMResponse(
            output=result.data,
            model_id=model_name,
            usage=usage,
        )
