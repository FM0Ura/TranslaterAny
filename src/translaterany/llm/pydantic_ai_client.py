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
from translaterany.llm.ollama_native import OllamaNativeClient

if TYPE_CHECKING:
    from translaterany.config.model import LLMConfig, ModelConfig

network_errors = [httpx.ConnectError, httpx.TimeoutException]
try:
    import openai

    network_errors.extend([openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError])
except ImportError:
    pass

try:
    from pydantic_ai.exceptions import ModelHTTPError

    network_errors.append(ModelHTTPError)
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
        self._ollama: dict[str, OllamaNativeClient] = {}

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
        elif model_cfg.provider == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            base_url = None

        # API key resolution
        api_key = provider_cfg.api_key
        if not api_key:
            if model_cfg.provider == "openai":
                api_key = os.environ.get("OPENAI_API_KEY")
            elif model_cfg.provider == "gemini":
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            elif model_cfg.provider == "ollama":
                api_key = "ollama"

        if model_cfg.provider != "ollama" and not api_key:
            raise LLMConfigError(
                f"Chave de API não configurada para o provedor '{model_cfg.provider}'. "
                "Defina api_key no config.toml ou variável de ambiente correspondente."
            )

        extra_args: dict[str, Any] = {"temperature": model_cfg.temperature}
        if model_cfg.provider == "ollama":
            if model_cfg.num_ctx:
                extra_args["extra_body"] = {"num_ctx": model_cfg.num_ctx}
        else:
            # Para provedores em nuvem (Gemini, OpenAI):
            # Não enviar num_ctx (parâmetro restrito ao Ollama) e desabilitar thinking se think=False
            if not model_cfg.think:
                extra_args.setdefault("extra_body", {})["reasoning_effort"] = "none"

        return model_cfg.model, base_url, api_key, extra_args

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        model_name, base_url, api_key, extra_args = self._resolve_model(request.model)
        model_cfg = self._model_config(request.model)
        if model_cfg.provider == "ollama":
            return self._generate_ollama(request, model_cfg, base_url or "http://localhost:11434")

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

        output_data = getattr(result, "output", None)
        if output_data is None:
            output_data = getattr(result, "data", None)

        raw_usage = result.usage if hasattr(result, "usage") and not callable(result.usage) else (result.usage() if callable(getattr(result, "usage", None)) else None)
        usage = Usage(
            input_tokens=getattr(raw_usage, "input_tokens", 0) or getattr(raw_usage, "request_tokens", 0) or 0,
            output_tokens=getattr(raw_usage, "output_tokens", 0) or getattr(raw_usage, "response_tokens", 0) or 0,
        )

        return LLMResponse(
            output=output_data,
            model_id=model_name,
            usage=usage,
        )


    def _model_config(self, alias: str) -> ModelConfig:
        profile = self.config.profiles.get(self.config.profile)
        if profile is not None and isinstance(getattr(profile, alias, None), str):
            alias = getattr(profile, alias)
        return self.config.models[alias]  # _resolve_model já validou

    def _generate_ollama[T: BaseModel](
        self, request: LLMRequest[T], model_cfg: ModelConfig, base_url: str
    ) -> LLMResponse[T]:
        """Ollama vai pela API nativa: o /v1 ignora num_ctx e não desliga o raciocínio."""
        client = self._ollama.get(base_url)
        if client is None:
            client = self._ollama[base_url] = OllamaNativeClient(base_url)
        return client.chat(
            model=model_cfg.model,
            instructions=request.instructions,
            prompt=request.prompt,
            output_type=request.output_type,
            num_ctx=model_cfg.num_ctx,
            temperature=request.temperature if request.temperature is not None else model_cfg.temperature,
            think=model_cfg.think,
        )
