# M2 — Camada de IA e tradução básica · Design

- **Marco:** M2 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-26
- **Status:** proposto (2026-09-26) · plano: pendente
- **Depende de:** M0 ([spec](2026-09-24-m0-fundacao-design.md)) e M1 ([spec](2026-09-24-m1-midia-legendas-design.md))

---

## 1. Objetivo

Implementar a camada real de inteligência artificial sobre `pydantic-ai-slim`, conectando-se a modelos locais via Ollama (em container Docker) e provedores em nuvem opcionais (Gemini / OpenAI). 

Ao fim do M2, a aplicação realiza a **primeira tradução real ponta a ponta** de um episódio:
`translaterany run <pasta>` extrai as legendas do MKV (M1), normaliza e classifica as linhas (M1), traduz os diálogos para português brasileiro fluente com o modelo local `translategemma:12b` (M2) e grava o arquivo `.pt-BR.ass` com timing, estilos e tags ASS perfeitamente preservados.

---

## 2. Fora do escopo

| Item | Onde |
|---|---|
| Memória da série (AniList, Jikan, glossário unificado, personagens) | M3 |
| Tradução de placas (`sign`), músicas (`song`) e telas | M4 |
| Atribuição de falantes e contexto visual de cena | M4 |
| Métricas automáticas e linha de base de qualidade | M5 |
| Revisão de sentido e ajuste de coloquialidade em etapas dedicadas | M6 |
| Coerência de tratamento e ortografia (LanguageTool) | M7 |
| Portões e laço fechado de QA com blame | M8 |

---

## 3. Evidências do ambiente e modelos

| Item | Estado / Característica | Implicação |
|---|---|---|
| **GPU** | NVIDIA GeForce RTX 3060 (12.288 MiB VRAM) | Roda confortavelmente modelos 12B/14B quantizados (Q4/Q5). Executar um modelo por etapa evita trocas constantes de VRAM. |
| **Ollama** | Rodando em container Docker (`ollama/ollama:latest`) em `http://localhost:11434` (porta 11434 mapeada para o host). | A aplicação acessa o Ollama via HTTP local (`http://localhost:11434/v1` para OpenAI-compatible e `/api/*` para tags/versão). |
| **Modelo de Tradução** | `translategemma:12b` já baixado no container. | Modelo de base Gemma afinado para tradução. Utilizado na etapa `translate_dialogue`. |
| **Modelo de Revisão** | `gemma4:12b` já baixado no container. | Modelo de raciocínio/geral configurado como padrão para as futuras etapas de revisão (M6/M7). |
| **Rede no Sandbox** | Comandos de teste em sandbox isolado bloqueiam conexões diretas de rede TCP. | Testes automatizados da suíte devem usar exclusivamente mocks e `FakeLLM`. Testes reais de fumaça ocorrem no ambiente da máquina. |

---

## 4. Decisões acordadas

| # | Decisão | Origem |
|---|---|---|
| **D1** | **Modelo local de tradução:** `translategemma:12b` via Ollama. | usuário |
| **D2** | **Modelo local de revisão/outras etapas:** `gemma4:12b` via Ollama. | usuário |
| **D3** | **Perfil padrão `local`:** 100% autônomo e sem custos; provedores Gemini e OpenAI são conectores opcionais, ativos apenas quando chaves forem fornecidas no config ou ambiente. | usuário |
| **D4** | **`LLMClient` via `pydantic-ai-slim`:** integração com o endpoint OpenAI-compatible do Ollama (`/v1`), garantindo validação de saída estruturada tipada por Pydantic v2. | usuário / arquitetura |
| **D5** | **Agrupamento dinâmico em blocos (chunking):** lotes de ~500 a 800 tokens de diálogo (~20 a 30 falas) + janela deslizante de 5 a 10 falas anteriores como contexto de leitura (`[CTX-n]`). | usuário |
| **D6** | **Cache de prefixo fixo:** instruções de sistema e diretrizes de tradução permanecem imutáveis para aproveitar o reuso de KV-cache no Ollama. | arquitetura |
| **D7** | **Cascata de recuperação em 4 níveis:** 1) Retry com `tenacity` em falhas transitórias; 2) Reconciliação imediata de IDs ausentes; 3) Bisseção recursiva do lote em metades em caso de JSON inválido ou alucinação; 4) Degradação graciosa mantendo texto original em inglês com aviso no log se uma fala atômica falhar. | usuário |
| **D8** | **Fallback de segurança contra censura:** quando provedores de nuvem recusarem requisições (comum em fan service de animes), redirecionamento automático daquele lote para o modelo local `translategemma`. | roadmap / decisão |
| **D9** | **Etapa `translate_dialogue` no pipeline:** consome `units.json` de `classify`, filtra apenas `type == "dialogue"`, substitui o texto traduzido e preserva tempos, estilos, atores e tags inline ASS intactos (`translates = True`). | pipeline |
| **D10** | **Diagnóstico completo (`doctor`):** checa status HTTP do container Ollama, presença de `translategemma:12b` e `gemma4:12b` em `/api/tags`, ferramentas de sistema (`ffmpeg`, `mkvmerge`) e chaves opcionais. | usuário / roadmap |
| **D11** | **Mensagens de erro do config em PT-BR:** erros de validação Pydantic no `config.toml` exibidos em português claro. | backlog M0 |
| **D12** | **Detecção de legendas Bazarr:** ignorar ou identificar corretamente faixas auxiliares como `.pt-BR.hi.srt` e `.forced.srt`. | backlog M1 |

---

## 5. Configuração (`config.toml` e modelos)

### 5.1 Estrutura do arquivo de configuração
O arquivo `~/.config/translaterany/config.toml` ganha a seção `[llm]`:

```toml
[llm]
profile = "local" # "local" | "hibrido" | "nuvem"
max_cost_usd = 5.0 # teto orçamentário de proteção quando usar nuvem

[llm.providers.ollama]
base_url = "http://localhost:11434/v1"
api_key = "ollama"

# Provedores de nuvem opcionais
[llm.providers.gemini]
api_key = "" # ou lido da variável de ambiente GEMINI_API_KEY

[llm.providers.openai]
api_key = "" # ou lido da variável de ambiente OPENAI_API_KEY

[llm.models.translategemma]
provider = "ollama"
model = "translategemma:12b"
num_ctx = 4096
temperature = 0.3

[llm.models.gemma4]
provider = "ollama"
model = "gemma4:12b"
num_ctx = 8192
temperature = 0.7

[llm.profiles.local]
translate = "translategemma"
review = "gemma4"

[llm.profiles.hibrido]
translate = "translategemma"
review = "gemini-flash"

[llm.profiles.nuvem]
translate = "gemini-flash"
review = "gemini-pro"
```

### 5.2 Modelos Pydantic (`config/model.py`)
Novos modelos para validação estrita com mensagens amigáveis em português:
- `ProviderConfig`: `base_url`, `api_key` (opcional).
- `ModelConfig`: `provider`, `model`, `num_ctx`, `temperature`.
- `ProfileConfig`: dicionário de tarefas (`translate`, `review`, etc.) mapeando para apelidos de modelos.
- `LLMConfig`: `profile`, `max_cost_usd`, dicionários de `providers`, `models` e `profiles`.

---

## 6. Camada de IA (`llm/`)

### 6.1 `PydanticAIClient`
A classe `PydanticAIClient` implementa o protocolo `LLMClient` definido no M0:
```python
class LLMClient(Protocol):
    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]: ...
```

- **Resolução de Modelo:** Dado `request.model` (ex.: `"translategemma"` ou perfil `"local"` + tag `"translate"`), busca a configuração em `llm.models`, identifica o provedor e instancia o modelo correspondente via `pydantic_ai.models.openai.OpenAIModel` (com `base_url="http://localhost:11434/v1"` para Ollama) ou conectores de nuvem.
- **Parâmetros de Requisição:** Configura `temperature`, `timeout` e `num_ctx` através dos argumentos de requisição suportados pelo backend.
- **Mapeamento de Exceções:** Converte falhas de conexão em `LLMTransientError`, recusas de segurança em `LLMRefusalError`, erros de schema em `LLMOutputError` e chaves inválidas em `LLMConfigError`.

---

## 7. Motor de Tradução e Agrupamento (`subtitles/translator.py`)

### 7.1 Esquemas de Dados para Diálogo
```python
class DialogueLine(BaseModel):
    id: str
    text: str


class ContextLine(BaseModel):
    text: str


class TranslationItem(BaseModel):
    id: str
    text: str


class TranslationBatch(BaseModel):
    items: list[TranslationItem]
```

### 7.2 Chunking Dinâmico e Janela Deslizante
- As unidades `dialogue` são agrupadas iterativamente.
- Cada lote contém no máximo `max_tokens_per_batch` (padrão: 800 tokens estimados, ~20 a 30 falas).
- Uma fila circular retém as últimas 5 a 10 falas traduzidas com sucesso para compor a seção de `context` no prompt seguinte, devidamente marcada como `[CONTEXTO - APENAS LEITURA]`.

### 7.3 Cascata de Resiliência em 4 Níveis
A execução de cada bloco segue um fluxo robusto:

1. **Nível 1 — Retentativas com `tenacity`:**
   Até 3 tentativas com backoff exponencial (1s, 2s, 4s) para falhas transitórias de conexão HTTP ou 503 da GPU.
2. **Nível 2 — Reconciliação de IDs ausentes:**
   Ao receber a resposta do modelo, o motor confere:
   `missing_ids = requested_ids - returned_ids`
   Se houver IDs ausentes, emite uma requisição complementar contendo apenas as falas que faltaram e funde os resultados.
3. **Nível 3 — Bisseção Recursiva:**
   Se a resposta gerar erro de schema JSON irrecuperável ou falha grave, o lote é dividido em duas metades: `batch[:n//2]` e `batch[n//2:]`. Cada metade é submetida de forma independente. Esse processo pode recursar até blocos de 1 fala.
4. **Nível 4 — Degradação Graciosa:**
   Se uma fala atômica (bloco unitário de 1 fala) ainda falhar, o motor registra um log `WARNING` com o ID da fala, preserva o texto original em inglês (`original_text`) e marca o campo `fallback_to_original: True` no manifesto, permitindo que a tradução do restante do episódio continue com sucesso.
5. **Tratamento de Recusa por Nuvem:**
   Se um provedor de nuvem gerar `LLMRefusalError` (filtro de segurança ativado por conteúdo ecchi/fan service), o lote em questão é automaticamente reencaminhado para o modelo local `translategemma:12b`.

---

## 8. Etapa de Pipeline: `translate_dialogue` (`stages/translate_dialogue.py`)

### 8.1 Integração ao Pipeline
- `name = "translate_dialogue"`
- `scope = "episode"`
- `translates: ClassVar[bool] = True` (sinaliza para as etapas subsequentes `write`, `publish` e `remux` que os dados contêm uma tradução real).
- `inputs = ["classify"]`
- `enabled_by_default = True`

### 8.2 Comportamento de Execução
1. Carrega o artefato `units.json` emitido pela etapa `classify`.
2. Separa as unidades de `type == "dialogue"`. Demais unidades (`sign`, `song`, `karaoke`, `comment`) não sofrem tradução nesta etapa e são repassadas com seu texto intacto.
3. Passa os diálogos para o `DialogueBatchTranslator`.
4. Atualiza os nós de texto das unidades traduzidas, preservando rigorosamente:
   - `start_ms` e `end_ms` (timing original);
   - `style`, `layer`, `actor`, `margin_l`, `margin_r`, `margin_v`;
   - Tags inline ASS (como `{\pos(x,y)}`, `{\fad(100,100)}`, etc.), garantindo que os modificadores visuais fiquem intactos.
5. Grava o artefato `translated_units.json` no diretório de dados do episódio.
6. Registra no `manifest.json`:
   - Hash dos dados de entrada + hash da configuração do modelo + hash do prompt de tradução;
   - Tokens consumidos (`input_tokens`, `output_tokens`, `cached_input_tokens`);
   - Modelo utilizado e falas que eventualmente caíram em fallback.

---

## 9. Diagnóstico e CLI (`cli/doctor.py`)

O comando `translaterany doctor` é estendido com verificações completas da stack de IA:
1. **Conectividade do Ollama:** `GET http://localhost:11434/api/version` → valida se o container Docker está rodando e acessível.
2. **Modelos Locais:** `GET http://localhost:11434/api/tags` → valida se `translategemma:12b` e `gemma4:12b` estão presentes na lista de modelos instalados.
3. **GPU NVIDIA:** `nvidia-smi` → reporta o modelo da placa (RTX 3060) e a quantidade de VRAM total/livre.
4. **Chaves de Nuvem (Opcional):** Se `GEMINI_API_KEY` ou `OPENAI_API_KEY` estiverem configuradas, testa autenticação básica com um ping leve.
5. **Ferramentas de Mídia:** Validação já existente de `ffmpeg`, `ffprobe`, `mkvextract` e `mkvmerge`.

---

## 10. Estratégia de Testes

### 10.1 Testes Automatizados (Sintéticos, Rápidos, sem Rede Externa)
Cobertos com `pytest` e `FakeLLM` mockando retornos estruturados:
- `test_config_llm.py`: valida parsing do `config.toml`, perfis `local`/`hibrido`/`nuvem`, apelidos de modelo e mensagens de erro amigáveis em português.
- `test_llm_client.py`: testa despacho de chamadas, serialização/deserialização do Pydantic, e mapeamento de exceções (`LLMTransientError`, `LLMRefusalError`, etc.).
- `test_chunking.py`: testa divisão dinâmica de falas por orçamento de tokens e formatação da janela deslizante de contexto.
- `test_translator_resilience.py`:
  - Simula timeout de rede → valida retry do `tenacity`;
  - Simula resposta omitindo IDs → valida requisição complementar de IDs faltantes e fusão correta;
  - Simula JSON malformado persistente → valida bisseção do lote em metades recursivas;
  - Simula falha total de uma fala individual → valida fallback para o texto em inglês com aviso no log;
  - Simula recusa por censura na nuvem → valida redirecionamento para o modelo local.
- `test_stage_translate_dialogue.py`: testa a etapa completa de episódio com `FakeLLM`, verificando a substituição dos textos em unidades de diálogo, preservação de tags inline e gravação de metadados no manifesto.
- `test_doctor_llm.py`: mock de respostas do Ollama e `nvidia-smi` para validar todas as ramificações do `doctor`.

### 10.2 Teste de Fumaça no Ambiente Real
- Execução manual de `translaterany run temporada-teste/Charlotte/Season\ 1/` (especificamente o primeiro episódio) utilizando o container Ollama ativo com `translategemma:12b`.
- Verificação do arquivo gerado `.pt-BR.ass` com um player de vídeo (ex.: `mpv` ou VLC), inspecionando naturalidade das falas, formatação dos diálogos e ausência de regressões em timing ou tags visuais.
