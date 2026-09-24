# M0 — Fundação · Design

- **Marco:** M0 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-24
- **Status:** aprovado (2026-09-24) · plano: [`2026-09-24-m0-fundacao.md`](../plans/2026-09-24-m0-fundacao.md)

---

## 1. Objetivo

Construir o esqueleto sobre o qual todas as etapas dos marcos seguintes serão plugadas: configuração, interface de etapa, runner, armazenamento de artefatos, cache/invalidação, retomada, CLI e a interface da camada de IA (com implementação falsa para testes).

Ao fim do M0 **não existe tradução nem IA real**. Existe um pipeline que executa etapas quaisquer, sobre episódios quaisquer, de forma retomável, cacheada e segura.

## 2. Fora do escopo

| Item | Marco |
|---|---|
| Varredura real da biblioteca, parsing `SxxEyy`, seleção de faixas, `.ass` | M1 |
| Tipos de linha e roteamento por tipo | M1 (quando existirem linhas) |
| Qualquer IA real, perfis de modelo, custo, `estimate` | M2 |
| Paralelismo de chamadas | M2, se necessário |
| Entradas "suaves" (não entram no hash; usadas para marcar episódios desatualizados) | M3 |
| Métricas | M5 |
| Portões e laço do QA | M8 |

## 3. Decisões tomadas neste spec (revisar)

| # | Decisão | Motivo |
|---|---|---|
| D1 | **Código e identificadores em inglês** (módulos, classes, nomes de etapas no config, ex.: `translate_dialogue`); **mensagens para o usuário em PT-BR** (CLI, erros, relatórios) | convenção do ecossistema Python; config legível por quem conhece o código |
| D2 | Diretório de dados padrão `~/.local/share/translaterany/` (respeita `XDG_DATA_HOME`), configurável | padrão Linux (XDG) |
| D3 | Config em `~/.config/translaterany/config.toml` (respeita `XDG_CONFIG_HOME`); sobrescrevível por `--config` ou `TRANSLATERANY_CONFIG` | padrão Linux (XDG) |
| D4 | **Runner processa por etapa** (todas as unidades passam pela etapa N antes da N+1) já no M0 | é o laço central do runner; antecipado do M2 |
| D5 | Etapas têm **escopo** `episode` ou `series` já no M0 | a Fase 1 (M3) depende disso; mudar depois alteraria o núcleo |
| D6 | Artefatos nomeados **pelo nome da etapa**, sem prefixo numérico (`normalize.json`, não `02_normalize.json`) | reordenar etapas não pode quebrar caminhos nem o cache |
| D7 | Interface de IA **síncrona** | runner sequencial; `pydantic-ai` oferece `run_sync`; concorrência pode ser adicionada no M2 atrás da mesma interface |
| D8 | Lock por série com `fcntl.flock` (Linux) | ambiente alvo é Linux; portabilidade não é objetivo da v1 |
| D9 | Descoberta de episódios **provisória** no M0: `run <pasta-da-série>` considera todo `*.mkv` sob a pasta; chave do episódio = caminho relativo | a descoberta real (`SxxEyy`, biblioteca inteira) é do M1 e substitui esta atrás da mesma interface |
| D10 | Ferramentas de desenvolvimento: `pytest` + `ruff` | mínimo necessário |

## 4. Estrutura de pacotes

```
src/translaterany/
├── __init__.py
├── cli/
│   ├── __init__.py        # exporta o app (entry point) e registra os comandos
│   ├── app.py             # app typer, opções globais, utilitários comuns
│   ├── run.py             # comando run
│   ├── status.py          # comando status
│   ├── retry.py           # comando retry
│   └── doctor.py          # comando doctor
├── config/
│   ├── __init__.py
│   ├── model.py           # modelos pydantic da configuração
│   └── loader.py          # localização, leitura TOML, validação, mensagens de erro
├── pipeline/
│   ├── __init__.py
│   ├── stage.py           # interface Stage, StageContext, exceções
│   ├── registry.py        # registro de etapas por nome
│   ├── units.py           # Series, Episode, descoberta (provisória no M0)
│   ├── artifacts.py       # ArtifactStore, InputReader, OutputWriter, ManifestSet
│   ├── manifest.py        # Manifest (modelo + leitura/escrita)
│   ├── cache.py           # cálculo da chave de cache
│   ├── runner.py          # Runner
│   ├── reset.py           # reprocessamento forçado (base do retry)
│   ├── status.py          # leitura de estado (base do status)
│   └── lock.py            # lock por série
├── llm/
│   ├── __init__.py
│   ├── client.py          # interface LLMClient, LLMRequest, LLMResponse, Usage
│   └── fake.py            # FakeLLM
├── stages/
│   ├── __init__.py        # importa e registra as etapas embutidas
│   └── inventory.py       # única etapa real do M0
├── util/
│   ├── fs.py              # escrita atômica, slug, hashing de arquivo
│   ├── doctor.py          # interface Check + checagens básicas
│   └── log.py             # logging em terminal + arquivo
├── memory/                # vazio no M0 (M3)
├── media/                 # vazio no M0 (M1)
└── subtitles/             # vazio no M0 (M1)
```

Entry point no `pyproject.toml`: `translaterany = "translaterany.cli:app"`.

Dependências do M0: `pydantic`, `typer` (traz `rich`). Dev: `pytest`, `ruff`.

## 5. Configuração

### 5.1 Formato

```toml
[general]
data_dir = "~/.local/share/translaterany"   # opcional
log_level = "INFO"                          # opcional

[pipeline]
stages = ["inventory"]                      # ordem de execução

[stages.inventory]
enabled = true                              # opcional, padrão true
[stages.inventory.options]                  # opções próprias da etapa, validadas pelo modelo dela
```

- Sem arquivo de config, usa-se um **config padrão embutido** (pipeline com as etapas disponíveis no marco atual).
- `enabled = false` remove a etapa da execução sem tirá-la da lista.

### 5.2 Validação

Feita ao iniciar qualquer comando, com pydantic. Erros apontam **arquivo, caminho da chave e problema**, em PT-BR:

```
Erro no config (~/.config/translaterany/config.toml):
  stages.translate_dialogue.options.block_tokens: esperado número inteiro, recebido "grande"
```

Regras validadas:
1. todo nome em `pipeline.stages` existe no registro de etapas;
2. sem nomes repetidos;
3. `[stages.X]` para etapa inexistente → erro (evita erro de digitação silencioso);
4. `options` de cada etapa validadas pelo modelo `Options` da própria etapa;
5. **dependências:** toda entrada declarada por uma etapa (`inputs`) aponta para uma etapa **anterior e habilitada** no pipeline;
6. uma etapa de escopo `series` só pode depender de etapas anteriores (de qualquer escopo); uma de escopo `episode` pode depender de etapas `series` e `episode` anteriores.

## 6. Unidades de trabalho

```python
@dataclass(frozen=True)
class Series:
    key: str            # slug estável
    name: str           # nome da pasta
    root: Path          # caminho absoluto da pasta

@dataclass(frozen=True)
class Episode:
    series: Series
    key: str            # M0: caminho relativo slugificado; M1: "S01E04"
    source: Path        # caminho absoluto do .mkv
```

**Slug** (`util.fs.slugify`): minúsculas, qualquer sequência de caracteres não alfanuméricos Unicode → `-`, sem hífens nas pontas, mais sufixo de 6 caracteres do SHA-256 do nome original para evitar colisão (ex.: `High School D×D (2012)` → `high-school-d-d-2012-1a2b3c`). Unicode no caminho de origem é preservado em `root`/`source`; o slug é só para o diretório de dados.

**Descoberta provisória** (`units.discover(path) -> tuple[Series, list[Episode]]`): a pasta passada é a série; episódios = todos os `*.mkv` sob ela (recursivo), ordenados pelo caminho. É uma função isolada, substituída no M1.

## 7. Interface de etapa

```python
class StageScope(StrEnum):
    EPISODE = "episode"
    SERIES = "series"

class Stage(ABC):
    name: ClassVar[str]                 # identificador único (config, artefatos, manifest)
    version: ClassVar[str]              # mudar = invalidar cache (lógica ou prompt mudou)
    scope: ClassVar[StageScope]
    inputs: ClassVar[tuple[str, ...]] = ()   # etapas cujos artefatos esta lê
    reads_source: ClassVar[bool] = False     # lê o arquivo de origem diretamente (entra no hash)
    Options: ClassVar[type[BaseModel]] = NoOptions

    def __init__(self, options: BaseModel) -> None: ...

    @abstractmethod
    def run(self, ctx: StageContext) -> None:
        """Lê entradas via ctx, grava exatamente um artefato via ctx.output."""

    def doctor_checks(self) -> list[Check]:
        return []                       # etapas contribuem com verificações próprias
```

```python
@dataclass
class StageContext:
    series: Series
    episode: Episode | None             # None quando scope == SERIES
    episodes: list[Episode]             # todos os episódios da série (útil para etapas de série)
    inputs: InputReader                 # leitura de artefatos das etapas declaradas em `inputs`
    output: OutputWriter                # gravação do artefato desta etapa
    llm: LLMClient
    log: logging.Logger
```

- `InputReader.json(stage_name, Model) -> Model` e `InputReader.path(stage_name) -> Path`. Ler uma etapa que não está em `inputs` gera erro (garante que o hash de cache está completo).
- Para uma etapa `series` que depende de uma etapa `episode`, `InputReader.json_all(stage_name, Model) -> dict[episode_key, Model]`.
- `OutputWriter.json(model)` ou `OutputWriter.file(suffix, data: bytes)`. Grava de forma atômica. Chamar zero ou duas vezes é erro.

**Exceções que a etapa pode lançar:**

| Exceção | Efeito |
|---|---|
| `SkipEpisode(reason)` | episódio marcado `skipped` com o motivo; as etapas seguintes o ignoram. Só válida em etapa `episode` |
| qualquer outra | a unidade é marcada `failed` com o erro; as etapas seguintes a ignoram; o runner **continua** com as demais unidades |
| `KeyboardInterrupt` | ver 10.4 |

**Registro:** decorador `@register_stage` em `pipeline/registry.py`; `stages/__init__.py` importa as etapas embutidas. Nome duplicado no registro é erro na importação.

### 7.1 Etapa `inventory` (única etapa real do M0)

Escopo `episode`, sem entradas, `reads_source = True`. Grava `inventory.json` com: caminho de origem, tamanho e **impressão digital** do arquivo (SHA-256 de tamanho + primeiro MiB + último MiB). Serve para exercitar o pipeline de ponta a ponta e será a base da detecção de "release trocada" no M1.

## 8. Armazenamento

```
<data_dir>/
├── series/<series-key>/
│   ├── series.json                  # nome e caminho de origem
│   ├── .lock
│   ├── manifest.json                # manifest das etapas de escopo series
│   ├── stages/<stage>.json          # artefatos de etapas series
│   └── episodes/<episode-key>/
│       ├── manifest.json
│       └── <stage>.json | <stage>.<ext>
└── logs/run-<AAAAMMDD-HHMMSS>.log
```

**Escrita atômica** (`util.fs.atomic_write`): grava em `<nome>.tmp-<pid>` no mesmo diretório, `fsync`, `os.replace`. Arquivos `.tmp-*` restantes de execuções interrompidas são removidos ao abrir a unidade.

## 9. Manifest e chave de cache

### 9.1 Manifest

```json
{
  "schema": 1,
  "unit": {"series": "charlotte-2015-9f1c2e", "episode": "season-1-s01e01-...", "source": "/.../S01E01....mkv"},
  "status": "ok",
  "skip_reason": null,
  "stages": {
    "inventory": {
      "status": "done",
      "key": "sha256:…",
      "artifact": "inventory.json",
      "artifact_hash": "sha256:…",
      "started_at": "2026-09-24T12:00:00Z",
      "finished_at": "2026-09-24T12:00:01Z",
      "duration_s": 0.8,
      "error": null
    }
  }
}
```

- `status` da unidade: `ok` | `skipped` | `failed`.
- `status` da etapa: `done` | `failed`. Etapas nunca executadas não aparecem.
- Gravado atomicamente **depois** do artefato. Um artefato sem registro no manifest é tratado como inexistente.
- `schema` permite migração futura; versão desconhecida → erro claro.

### 9.2 Chave de cache

```
key = sha256( canonical_json({
    "stage": name,
    "version": version,
    "options": options.model_dump(mode="json"),
    "inputs": { nome_da_entrada: artifact_hash, ... },   # em ordem de nome
    "source": fingerprint                                # só se reads_source == True
}))
```

- Para uma etapa `series` que depende de uma etapa `episode`, o valor da entrada é o hash da lista ordenada de pares `(episode_key, artifact_hash)` de todos os episódios `ok`. Adicionar, remover ou alterar um episódio invalida a etapa de série.
- `fingerprint` é a impressão digital do arquivo de origem (ver 7.1), calculada uma vez por episódio por execução.

Uma etapa **é pulada** para uma unidade quando o manifest registra `status: done` com a mesma `key` e o artefato existe com o mesmo `artifact_hash`. Caso contrário, executa.

**Consequência desejada:** a invalidação se propaga **pelo conteúdo**. Se uma etapa reexecuta e produz artefato idêntico, as seguintes continuam em cache. Se muda, as que dependem dela reexecutam; as que não dependem, não.

`canonical_json`: chaves ordenadas, sem espaços, UTF-8.

## 10. Runner

### 10.1 Laço principal (por etapa)

```
para cada etapa habilitada, na ordem do pipeline:
    se escopo == series:
        executar_se_necessário(série)
    senão:
        para cada episódio ainda "ok":
            executar_se_necessário(episódio)
```

A série também tem status: se uma etapa `series` falha, as etapas seguintes não rodam para a série inteira.

### 10.2 Execução de uma unidade

1. calcula a chave (lê hashes das entradas nos manifests);
2. se em cache → registra "pulado (cache)" no log e segue;
3. senão, executa a etapa, grava artefato, atualiza manifest com `done`;
4. em exceção → registra `failed` (ou `skipped`) com mensagem e traceback no log; segue para a próxima unidade.

**Na execução seguinte:** unidades `failed` voltam a `ok` no início do `run` e tentam de novo a partir da etapa que falhou (as anteriores estão em cache). Unidades `skipped` **continuam puladas** até um `retry` explícito.

### 10.3 Resultado da execução

Ao final, resumo no terminal: unidades ok / puladas / com falha, por etapa. Código de saída: `0` se nenhuma falha; `1` se houve falha (inclusive manifest corrompido, com mensagem clara e sem traceback); `2` erro de config/uso/ambiente; `130` interrompido.

### 10.4 Interrupção (Ctrl+C)

O artefato da etapa em andamento não chega a ser renomeado (escrita atômica) e o manifest não é atualizado, então a etapa fica como não executada. O runner libera o lock e sai com `130`. Rodar `run` de novo retoma exatamente dali.

### 10.5 Lock

`series/<key>/.lock` com `fcntl.flock(LOCK_EX | LOCK_NB)`. Se já estiver travado: mensagem "Série X já está sendo processada por outra execução" e a série é ignorada nesta execução. O lock é do sistema operacional: liberado automaticamente se o processo morrer.

### 10.6 Reprocessamento forçado

`retry` apaga do manifest o registro da etapa indicada e de todas as seguintes **de qualquer escopo** (não apaga artefatos; eles serão sobrescritos), e zera `status`/`skip_reason` das unidades afetadas. A próxima execução refaz dali. Se a etapa indicada for de escopo `series`, `--episode` não é permitido.

## 11. Camada de IA (interface)

`Usage`, `LLMRequest` e `LLMResponse` são `dataclass` (estruturas internas, sem necessidade de validação):

```python
@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

@dataclass(frozen=True)
class LLMRequest[T: BaseModel]:
    model: str                      # apelido de modelo (resolvido no M2)
    instructions: str               # prefixo fixo (cacheável)
    prompt: str                     # parte variável
    output_type: type[T]
    temperature: float | None = None
    tag: str = ""                   # rótulo livre para logs/métricas (ex.: nome da etapa)

@dataclass(frozen=True)
class LLMResponse[T: BaseModel]:
    output: T
    model_id: str                   # modelo efetivamente usado
    usage: Usage = field(default_factory=Usage)

class LLMClient(Protocol):
    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]: ...
```

Erros padronizados (usados por todas as implementações): `LLMTransientError` (pode tentar de novo), `LLMOutputError` (resposta inválida após as tentativas), `LLMRefusalError` (recusa por filtro de segurança), `LLMConfigError`.

**`FakeLLM`** (para testes):
- recebe uma lista de respostas roteirizadas **ou** uma função `(request) -> T | Exception`;
- lança a exceção quando o roteiro contém uma (simula falhas);
- guarda todas as requisições recebidas em `.calls` para asserções;
- `usage` sintético (tamanho do texto / 4).

No M0 o `StageContext.llm` recebe um `FakeLLM` sem roteiro que lança `LLMConfigError("nenhum provedor configurado")` se chamado. A implementação real entra no M2.

## 12. CLI

| Comando | Comportamento no M0 |
|---|---|
| `translaterany run <pasta-da-série>` | descobre episódios, adquire lock, executa o pipeline, mostra progresso e resumo |
| `translaterany status [<pasta-da-série>]` | tabela: episódio, última etapa concluída, status (ok/skipped/failed) e motivo. Sem argumento: todas as séries conhecidas no diretório de dados |
| `translaterany retry <pasta-da-série> [--episode <chave>] --from <etapa>` | reprocessamento forçado (10.6); sem `--episode`, vale para todos os episódios da série |
| `translaterany doctor` | executa as verificações (seção 13) e mostra ✅/⚠️/❌ |

Opções globais: `--config <arquivo>`, `--data-dir <pasta>`, `--verbose`.

Progresso com `rich`: barra por etapa ("inventory: 12/13").

## 13. Doctor

```python
@dataclass
class CheckResult:
    status: Literal["ok", "warn", "fail"]
    message: str

class Check(Protocol):
    name: str
    def run(self) -> CheckResult: ...
```

Verificações do M0: versão do Python ≥ 3.14; config válido; diretório de dados gravável. Cada etapa habilitada contribui com as suas via `doctor_checks()` (a partir do M1: `ffprobe`, `mkvextract`…).

Toda execução de `run` roda o doctor antes e **aborta se houver `fail`**, mostrando o problema.

## 14. Logging

- `logging` da biblioteca padrão.
- Terminal: nível do config (`INFO` padrão; `--verbose` = `DEBUG`), formatado com `rich`.
- Arquivo: `logs/run-<timestamp>.log`, sempre `DEBUG`, com tracebacks completos.

## 15. Testes

Tudo com `pytest`, sem rede, sem IA real, em diretórios temporários. Etapas fictícias definidas nos próprios testes.

| Área | Casos |
|---|---|
| Config | padrão sem arquivo; etapa inexistente; nome repetido; `[stages.X]` órfão; opção inválida (mensagem com caminho da chave); dependência fora de ordem ou desabilitada |
| Registro | nome duplicado; etapas embutidas registradas |
| Slug | ASCII, Unicode (`×`, `☆`), colisões distintas geram slugs distintos, estabilidade |
| Escrita atômica | arquivo final nunca parcial; `.tmp-*` limpos na abertura |
| Cache | segunda execução não roda nada; mudar opção de uma etapa reexecuta ela e **só** as que dependem dela; etapa que regenera artefato idêntico não invalida as seguintes; mudar `version` invalida; mudar o arquivo de origem invalida a etapa sem entradas |
| Runner | ordem por etapa; etapa `series` vê artefatos de todos os episódios; falha num episódio não para os outros; `SkipEpisode` pula etapas seguintes; falha em etapa `series` para a série |
| Interrupção | etapa fictícia lança `KeyboardInterrupt` no 3º episódio → código 130; nova execução retoma no 3º e não refaz 1º e 2º |
| Lock | segunda aquisição simultânea falha com mensagem; lock liberado após término |
| Retry | `--from` refaz a etapa e as seguintes; `--episode` limita a um episódio |
| FakeLLM | respostas roteirizadas; exceções roteirizadas; registro de chamadas |
| CLI | `run`, `status`, `retry`, `doctor` via `typer.testing.CliRunner`; códigos de saída |
| Inventory | impressão digital muda quando o conteúdo muda; arquivos pequenos (< 2 MiB) |

Arquivos de "episódio" nos testes são arquivos binários pequenos gerados na hora com extensão `.mkv` (o M0 não os interpreta).

## 16. Critérios de pronto

1. `uv run pytest` passa; `uv run ruff check` sem erros.
2. `translaterany run temporada-teste/"Charlotte (2015)"` executa `inventory` nos 14 episódios; a segunda execução não executa nada (tudo em cache).
3. Interromper com Ctrl+C no meio e rodar de novo completa só o que faltava.
4. `translaterany status` mostra os 14 episódios com `inventory` concluída.
5. `translaterany retry … --from inventory` força a reexecução.
6. `translaterany doctor` mostra as verificações do M0 com ✅.

## 17. Pontos de extensão previstos

| Ponto | Quem usa |
|---|---|
| `units.discover` substituível | M1 (varredura real, `SxxEyy`, biblioteca inteira) |
| `Stage.doctor_checks` | M1 (ffprobe/mkvtoolnix), M2 (Ollama/chaves), M7 (LanguageTool) |
| `LLMClient` | M2 (implementação com `pydantic-ai-slim`) |
| `Stage.version` + chave de cache | M2+ (versão do prompt; modelo resolvido entra nas `options` efetivas) |
| Entradas "suaves" fora do hash | M3 (glossário editado → episódio desatualizado, sem reexecução automática) |
| Escopo `series` | M3 (extração → consolidação) |
| Manifest `stages.*` | M5 (métricas por etapa) |
