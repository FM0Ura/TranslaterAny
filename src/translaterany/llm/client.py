"""Interface da camada de IA. As etapas dependem só disto, nunca de uma biblioteca de IA."""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Base dos erros da camada de IA."""


class LLMTransientError(LLMError):
    """Falha temporária (timeout, limite de requisições); pode tentar de novo."""


class LLMOutputError(LLMError):
    """Resposta inválida mesmo após as tentativas de correção."""


class LLMRefusalError(LLMError):
    """O provedor recusou a requisição (ex.: filtro de segurança)."""


class LLMConfigError(LLMError):
    """Configuração ausente ou inválida (provedor, modelo, chave)."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class LLMRequest[T: BaseModel]:
    model: str  # apelido de modelo (resolvido no M2)
    instructions: str  # prefixo fixo, cacheável
    prompt: str  # parte variável
    output_type: type[T]
    temperature: float | None = None
    tag: str = ""  # rótulo livre para logs/métricas (ex.: nome da etapa)


@dataclass(frozen=True)
class LLMResponse[T: BaseModel]:
    output: T
    model_id: str
    usage: Usage = field(default_factory=Usage)


class LLMClient(Protocol):
    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]: ...
