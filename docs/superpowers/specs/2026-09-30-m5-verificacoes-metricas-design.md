# M5 — Verificações e métricas · Design

- **Marco:** M5 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-30
- **Status:** proposto (2026-09-30) · plano: pendente
- **Depende de:** M0 ([spec](2026-09-24-m0-fundacao-design.md)), M1 ([spec](2026-09-24-m1-midia-legendas-design.md)), M2 ([spec](2026-09-26-m2-camada-ia-traducao-design.md)), M3 ([spec](2026-09-26-m3-memoria-serie-design.md)) e M4 ([spec](2026-09-27-m4-traducao-contextual-design.md))

---

## 1. Objetivo

**Medir antes de refinar.** O M5 cria a linha de base de qualidade contra a qual M6–M8 serão comparados:

1. Um módulo de **checagens** determinísticas, sem IA e sem I/O, reutilizável pela triagem (M6), pelos portões e pelo QA (M8);
2. **Métricas camada 1 (processo):** chamadas de IA, tokens, custo, tempo, erros, recusas e contadores específicos de cada etapa, persistidos no manifest;
3. **Métricas camada 2 (indicadores):** checagens aplicadas a cada instantâneo de texto do pipeline (o que cada etapa entregou e o estado acumulado depois dela), gravadas em `metrics.json` por episódio;
4. Comando **`translaterany report`** por série, por episódio e por modelo, com saída em JSON e comparação com uma linha de base salva.

O M5 **só mede**: nenhuma etapa passa a corrigir texto por causa das checagens.

---

## 2. Fora do escopo

| Item | Onde |
|---|---|
| Conflitos de gênero/tratamento via spaCy (e a dependência spaCy) | M7, junto da etapa de coerência |
| Triagem, resposta só com edições, taxa de triagem/edição das etapas de refinamento | M6 (o M5 deixa os contadores e o delta prontos) |
| Portões, laço do QA, *blame* | M8 |
| Métricas camada 3 (COMETKiwi, IA como juiz) e `eval` | depois da v1 |
| Relatório HTML/gráficos | descartado no brainstorming (terminal + JSON bastam) |
| Checagens de duração mínima/máxima de evento | fora: medem o timing do fansub, que o pipeline nunca altera |

---

## 3. Evidências do código atual

| Item | Situação | Implicação |
|---|---|---|
| Uso de tokens | `Usage` é devolvido pelo `LLMClient`, mas só somado em memória (`DialogueBatchTranslator.total_usage`); **nada é persistido** | camada 1 precisa de um medidor que não dependa das etapas |
| `StageRecord` | guarda apenas status, chave, hash, horários e `duration_s` | ganha campos `llm` e `counters` (schema 2) |
| Preços | `cli/estimate.py` usa valores fixos no código (0,15/0,60 USD por Mtok) | tabela de preços vai para o `ModelConfig` |
| Ids de frases unidas | `translate_dialogue` grava chaves compostas (`u1+u2`); só `redistribute_sentences` volta aos ids das unidades | a camada 2 resolve ids compostos via `merge_sentences` |
| Fontes | `select_track` só **lista** os anexos; nenhuma etapa os extrai | `quality_checks` extrai as fontes (via `mkvextract`) para um diretório temporário |
| Bug | `redistribute_sentences` usa `getattr(episode, "id", "")`, mas `Episode` tem `key` — a TM grava entradas sem episódio | corrigido no M5 (§9) |

---

## 4. Decisões acordadas

| # | Decisão | Origem |
|---|---|---|
| **D1** | **Escopo "núcleo leve"** de checagens: regras puras em Python + `fonttools`. spaCy fica para o M7. | Usuário |
| **D2** | **Padrão Netflix PT-BR** para velocidade de leitura: CPS máx. **17**, CPL máx. **42**, no máximo **2 linhas**. Exceder é `error` (sem faixa intermediária de aviso). | Usuário |
| **D3** | **Abordagem A:** `MeteredLLM` no runner grava a camada 1 no manifest; etapa `quality_checks` grava a camada 2 em `metrics.json`; `report` junta os dois. | Usuário |
| **D4** | `report` com saída em **terminal (rich) + `--json`**; `--baseline` compara com uma linha de base salva. Sem HTML. | Usuário |
| **D5** | `quality_checks` roda **no fim do pipeline** (depois de `publish`/`remux`): uma falha nela nunca impede a legenda de ser gravada. | Design |
| **D6** | Custo calculado **no momento da chamada** com os preços do `ModelConfig`, e gravado — o custo histórico não muda se os preços mudarem. | Design |
| **D7** | Instantâneos de texto descobertos automaticamente: etapas declaram `produces_texts = True`; o loader informa à `quality_checks` as etapas anteriores via `bind_pipeline`. | Design |
| **D8** | Linhas de base versionadas em `docs/baselines/` contêm **só números agregados** — nunca trechos de legenda. | Design / regra do projeto |

---

## 5. Módulo `translaterany.checks`

Pacote novo, puro (sem IA, sem acesso a disco, sem rede).

### 5.1 Modelos

```python
type Severity = Literal["info", "warn", "error"]

class LineInput(BaseModel):
    id: str                  # id da unidade ou id composto ("u1+u2")
    line_type: str           # dialogue, sign, song, ...
    style: str
    source: str              # EN com marcadores ⟦n⟧
    target: str              # PT-BR com marcadores ⟦n⟧
    duration_ms: int         # menor duração entre os eventos da unidade; soma nas compostas

class CheckEnv(BaseModel):
    glossary: list[GlossaryEntry]        # glossário filtrado do episódio
    names: list[str]                     # nomes + aliases de characters.yaml
    limits: ChecksConfig                 # limites do config

class Finding(BaseModel):
    check: str
    unit_id: str | None                  # None em checagens de episódio
    severity: Severity
    message: str                         # em PT-BR
    value: float | None = None           # ex.: CPS medido
```

Checagens de linha implementam `LineCheck` (`name`, `line_types`, `run(line, env) -> list[Finding]`) e ficam num registro `CHECKS`. `run_line_checks(lines, env) -> list[Finding]` aplica todas as habilitadas; uma checagem que lança exceção gera `Finding(check="check_crashed", severity="error", ...)` em vez de propagar.

### 5.2 Checagens de linha

Os textos são comparados **sem tags ASS e sem marcadores**, exceto em `markers`. Quebras `\N`/`\n` contam como separador de linha.

| Checagem | Regra | Severidade | Tipos |
|---|---|---|---|
| `markers` | multiconjunto de `⟦n⟧` do PT ≠ do EN | error | todos |
| `untranslated` | PT idêntico ao EN (ignorando caixa/espaços), ou ≥ 50% das palavras do PT em lista de palavras funcionais inglesas (*the, and, you, is, to, of, what, I…*) com ≥ 3 palavras | error | dialogue, sign |
| `length_ratio` | `len(PT)/len(EN)` fora de `[0.5, 2.0]`, só se `len(EN) ≥ 10` | warn | dialogue |
| `numbers` | sequência de algarismos do EN ausente no PT | warn | dialogue, sign |
| `negation` | EN com negação (*not, n't, never, no, nobody, nothing, none, neither, nor, without*) e PT sem (*não, nunca, nem, nada, ninguém, nenhum(a), jamais, sem*) | warn | dialogue |
| `names` | nome/alias de personagem presente no EN (palavra inteira) e ausente no PT | warn | dialogue |
| `glossary` | termo/alias do glossário no EN e a forma esperada ausente no PT (`translation`, ou `term` quando `keep_original`) | warn | dialogue, sign |
| `reading_speed` | CPS = caracteres visíveis (sem espaços nas pontas; espaços internos contam) / `duration_ms`·1000 > `max_cps`; CPL > `max_cpl`; nº de linhas > `max_lines` — um `Finding` por violação, com `value` | error | dialogue |
| `foreign_markers` | PT-PT: *autocarro, comboio, telemóvel, equipa, facto, ecrã, rapariga, casa de banho, pequeno-almoço, está a / estou a / estão a + infinitivo*; espanhol: *¿, ¡, pero, muy, también, usted, gracias, hola, ñ* — palavra inteira, sem diferenciar caixa | warn | dialogue, sign |

As listas de palavras ficam em `checks/lexicon.py`, fáceis de ampliar.

### 5.3 Checagem de episódio: `font_glyphs`

`check_font_glyphs(texts_by_font: dict[str, set[str]], fonts: dict[str, Path]) -> list[Finding]`

- `texts_by_font` agrupa os caracteres PT-BR usados por nome de fonte: a fonte do estilo do evento e as trocadas por `\fn` no prefixo/tags do evento.
- `fonts` mapeia nome de família (lido da tabela `name` via fontTools, sem diferenciar caixa) → arquivo extraído.
- Fonte com caracteres sem glifo no `cmap` → `warn` listando até 10 caracteres ausentes.
- Fonte usada mas não anexada → `info` (o player usará uma fonte do sistema).
- Arquivo de fonte ilegível → `info`.
- Nunca passa de `warn`.

### 5.4 Configuração

```toml
[checks]
max_cps = 17.0
max_cpl = 42
max_lines = 2
length_ratio = [0.5, 2.0]
length_ratio_min_chars = 10
disabled = []          # nomes de checagens a desligar, ex.: ["foreign_markers"]
```

Novo `ChecksConfig` em `config/model.py`, seção `checks` do `AppConfig`. Nome desconhecido em `disabled` é erro de configuração com mensagem clara.

---

## 6. Camada 1 — medidor de processo

### 6.1 `MeteredLLM` (`llm/metered.py`)

Envoltório de `LLMClient` criado pelo runner **por par (etapa, unidade)** e colocado em `ctx.llm`.

```python
class ModelStats(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0

class LLMStats(BaseModel):
    calls: int = 0
    errors: dict[str, int] = {}          # "transient" | "output" | "refusal" | "config" | "other"
    by_model: dict[str, ModelStats] = {} # chave: model_id devolvido (ou o apelido, se a chamada falhou)
    # totais derivados como propriedades: input_tokens, output_tokens, cost_usd
```

- A cada `generate`: incrementa `calls`; no sucesso soma tokens e custo em `by_model[response.model_id]`; em exceção incrementa `errors[tipo]` e **relança** (comportamento das etapas inalterado).
- Custo: `(input_tokens·in_price + output_tokens·out_price) / 1_000_000`. Tokens de entrada em cache são cobrados como entrada comum no M5 (sem desconto); `cached_input_tokens` fica registrado para quando houver provedor com desconto.
- Preços vêm de uma função `price_of(alias) -> (in, out)` injetada pelo runner, resolvida a partir de `LLMConfig.models`. Apelido desconhecido → custo 0.

### 6.2 Preços no config

`ModelConfig` ganha `input_price_per_mtok: float = 0.0` e `output_price_per_mtok: float = 0.0`. O `estimate` passa a usar esses campos em vez dos valores fixos.

### 6.3 Contadores das etapas

`StageContext` ganha `metrics: StageMetrics` com `count(name: str, n: int = 1)`. Contadores adotados no M5:

| Etapa | Contadores |
|---|---|
| `translate_dialogue`, `translate_signs`, `translate_songs` | `lines`, `fallback_original`, `markers_lost`, `ids_reconciled`, `batches_split` |
| `classify` | `ai_disambiguated` |
| `translation_memory` | `tm_candidates`, `tm_hits` |
| `merge_sentences` | `merged_groups`, `merged_units` |
| `redistribute_sentences` | `redistributed`, `tm_fed` |

`DialogueBatchTranslator` recebe um `StageMetrics` opcional para contar fallbacks, reconciliações e divisões onde elas acontecem.

### 6.4 Persistência no manifest (schema 2)

```python
class StageRecord(BaseModel):
    ...                                   # campos atuais
    llm: LLMStats | None = None           # None quando a etapa não chamou IA
    counters: dict[str, int] = {}
```

- `MANIFEST_SCHEMA = 2`. `load_manifest` aceita schema 1 e 2 (os campos novos têm padrão); o próximo `save` grava como 2. Outros valores continuam gerando `ManifestError`.
- **Cache:** num cache hit o registro não é tocado — os números sempre refletem a execução que produziu o artefato atual.
- **Falha:** o `StageRecord` `failed` também recebe `llm` e `counters` acumulados até a falha.
- O runner monta `ctx.llm`/`ctx.metrics` em `_context` e os recolhe em `_finish`/`_fail`.

---

## 7. Camada 2 — etapa `quality_checks`

### 7.1 Declaração

```python
class QualityChecksOptions(BaseModel):
    fonts: bool = True

class QualityChecksStage(Stage):
    name = "quality_checks"
    version = "1"
    scope = StageScope.EPISODE
    reads_source = True           # para extrair fontes anexadas
    inputs = ("normalize", "classify", "merge_sentences", "consolidate_memory", *snapshots)
```

- `Stage` ganha `produces_texts: ClassVar[bool] = False`; `translate_dialogue`, `translate_signs`, `translate_songs` e `redistribute_sentences` passam a declarar `True`.
- `Stage` ganha o gancho `bind_pipeline(self, previous: Sequence[Stage]) -> None` (padrão: não faz nada). O loader (`_build_stages`) chama-o logo após instanciar a etapa, com as etapas **habilitadas** que vêm antes, e só depois valida as entradas. `QualityChecksStage` usa-o para definir `self.snapshots` (as anteriores com `produces_texts`, na ordem do pipeline) e `self.inputs`.
- `merge_sentences` e `consolidate_memory` entram nas entradas só se estiverem habilitadas antes dela (sem eles: nenhum id composto; glossário/fichas vazios).
- `cache_payload` inclui o `ChecksConfig` — mudar limites recalcula as métricas.
- Entra no `DEFAULT_PIPELINE` como **última** etapa (depois de `remux`).

### 7.2 Montagem das linhas de um instantâneo

Para cada chave `k` do `UnitTexts` do instantâneo:
- **Id composto** (presente em `merge_sentences.units[].composite_id` com mais de uma unidade): `source = text_with_markers`, `duration_ms = sum(durations_ms)`, tipo/estilo da primeira unidade.
- **Id de unidade:** `source = Unit.text` do `normalize`, `duration_ms = min(end−start)` entre os eventos da unidade, tipo de `classify`, estilo da unidade.
- Chaves desconhecidas são ignoradas com aviso no log.

Glossário e nomes vêm de `MemoryStore` (mesmo filtro por episódio usado em `translate_dialogue`, extraído para uma função compartilhada em `memory/`).

### 7.3 Instantâneos, estado acumulado e delta

Para cada instantâneo, em ordem:
1. **Entregue:** checagens nas linhas que a etapa produziu → contagens por checagem e severidade.
2. **Estado acumulado:** `estado = estado_anterior ∪ textos_da_etapa` (a etapa sobrescreve). Ao entrar a chave de uma unidade que pertence a um id composto já no estado, o id composto sai do estado.
3. **Delta** entre o estado anterior e o novo, sobre as chaves presentes nos dois (mais as que entraram):
   - `changed`: chaves cujo texto mudou ou entrou;
   - `edit_ratio`: média de `1 − SequenceMatcher(a, b).ratio()` nas chaves presentes nos dois estados (0 se nenhuma);
   - `new` / `resolved`: achados (identificados por `(check, unit_id)`) que surgem/somem entre os dois estados.

O **estado final** é o estado acumulado após o último instantâneo.

### 7.4 Fontes

Com `fonts = true`: lê os anexos de fonte da origem (`mkvmerge -J`, tipos `font/*`, `application/x-truetype-font`, `application/vnd.ms-opentype`, `application/font-sfnt`, ou extensão `.ttf/.otf/.ttc`) e extrai-os com `mkvextract attachments` para um `TemporaryDirectory`. Os eventos do `normalize` dão estilo e `\fn`; a fonte de cada estilo vem do cabeçalho do `.ass` (`extract`). Qualquer falha de extração vira `Finding` `info` em `episode_checks` — nunca falha da etapa.

### 7.5 `metrics.json`

```json
{
  "schema": 1,
  "snapshots": [
    {
      "stage": "translate_dialogue",
      "lines": 377,
      "checks": {"reading_speed": {"error": 41}, "untranslated": {"error": 3}},
      "delta": {"changed": 377, "edit_ratio": 0.0, "new": 52, "resolved": 0}
    }
  ],
  "final": {
    "lines": 412,
    "by_type": {"dialogue": 377, "sign": 20, "song": 15},
    "checks": {"reading_speed": {"error": 41}},
    "flagged_lines": {"error": 44, "warn": 12},
    "reading_speed": {"cps_p50": 12.1, "cps_p95": 18.7, "cps_max": 26.0, "over_limit": 41,
                      "cps_histogram": [0, 3, 11, "…"]},
    "findings": [
      {"check": "negation", "unit_id": "u57", "severity": "warn", "message": "…", "value": null}
    ]
  },
  "episode_checks": [
    {"check": "font_glyphs", "unit_id": null, "severity": "warn", "message": "fonte 'X' sem glifos: ç, ã", "value": null}
  ]
}
```

`cps_histogram` conta as linhas de diálogo do estado final em faixas de 1 CPS (`[0,1)`, `[1,2)`, …, `[40,∞)` — 41 posições), permitindo percentis agregados por série sem guardar valores por linha.

A lista completa de `findings` só existe para o estado **final** (é o que M6/M8 vão consumir); instantâneos guardam só contagens. Modelos pydantic em `checks/metrics.py` (`EpisodeMetrics`, `SnapshotMetrics`, `FinalMetrics`).

---

## 8. Comando `report`

```
translaterany report <pasta> [--episode S01E03] [--json ARQUIVO] [--baseline ARQUIVO]
```

### 8.1 Agregação (`pipeline/report.py`, puro)

`build_report(store, series, episodes) -> SeriesReport` lê manifests (camada 1) e `metrics.json` (camada 2):

- **`stages`**: por etapa — episódios `done`/`failed`, tempo total e médio, `LLMStats` somado, contadores somados.
- **`models`**: por `model_id` — chamadas, tokens, custo, erros.
- **`final`**: por checagem — linhas afetadas e taxa por severidade; percentis de CPS da série calculados a partir da soma dos histogramas `reading_speed.cps_histogram` dos episódios.
- **`snapshots`**: por etapa de texto — `new`, `resolved` e `edit_ratio` médios/somados.
- **`worst_episodes`**: os 5 com maior taxa de linhas com `error`.
- **`missing_metrics`**: episódios sem `metrics.json`.

`SeriesReport` é pydantic, com `schema: int = 1`, e **não contém texto de legenda** (nem `findings`) — é seguro versionar como linha de base.

### 8.2 Saída

- Terminal (rich): tabelas *Processo por etapa*, *Por modelo*, *Indicadores finais*, *Instantâneos*, *Piores episódios*, e a lista de episódios sem métricas.
- `--episode`: mesma visão para um episódio + tabela dos achados finais (id, checagem, severidade, mensagem, trecho do PT de até 60 caracteres). Só no terminal.
- `--json ARQUIVO`: grava o `SeriesReport`.
- `--baseline ARQUIVO`: carrega um `SeriesReport` salvo e mostra, ao lado de cada checagem e métrica de processo, o delta com ▲ (piorou) / ▼ (melhorou).

### 8.3 Erros e códigos de saída

| Situação | Comportamento |
|---|---|
| Nenhum episódio com `metrics.json` | mensagem "Nenhuma métrica encontrada — rode `translaterany run` primeiro." · código 1 |
| `metrics.json` corrompido ou de schema desconhecido | episódio listado em "sem métricas" com aviso; agregados seguem · código 0 |
| `--baseline` ilegível ou de schema incompatível | mensagem clara · código 2 |
| Manifest inválido | mesma mensagem de `status` (`ManifestError`) · código 1 |

---

## 9. Correção incluída

`redistribute_sentences`: `ep_id = getattr(episode, "id", "")` → `episode.key`, para que as entradas da TM registrem o episódio. Teste de regressão incluso.

---

## 10. Pipeline no M5

```
… (M4 inalterado) …
redistribute_sentences
  ↓
write → publish → remux (opcional)
  ↓
quality_checks   (novo; lê os instantâneos translate_* e redistribute_sentences)
```

`report` é um comando, não uma etapa.

---

## 11. Estratégia de testes

Todos sintéticos; nenhum trecho real de legenda.

1. `test_checks_*.py`: casos positivos e negativos de cada checagem; limites exatos (CPS 17,0 passa, 17,1 falha; CPL 42/43; 2/3 linhas); tags e `\N` ignorados na contagem; `disabled`; `check_crashed`.
2. `test_font_glyphs.py`: fonte mínima gerada com fontTools no teste (sem binário no repositório): glifo presente, ausente, fonte não anexada, arquivo ilegível.
3. `test_metered_llm.py`: tokens e custo por modelo com `FakeLLM`; erros contados por tipo e relançados; apelido sem preço → custo 0.
4. `test_runner_metrics.py`: `llm`/`counters` no `StageRecord`; preservados em cache hit; gravados na falha; manifest schema 1 lido e regravado como 2.
5. `test_quality_checks_stage.py`: resolução de ids compostos; estado acumulado com troca composto → unidades; delta (`changed`, `edit_ratio`, `new`, `resolved`); descoberta de instantâneos via `bind_pipeline` (inclusive com uma etapa de texto desabilitada); `cache_payload` sensível aos limites.
6. `test_report.py`: agregação multi-episódio; `--json` → `--baseline` (ida e volta); episódios sem métricas; códigos de saída.
7. `test_config_checks.py`: seção `[checks]` válida/inválida; preços no `ModelConfig`; `estimate` usando os preços do config.
8. `test_redistribute_tm_episode.py`: regressão do bug da §9.
9. `test_m5_e2e.py`: pipeline sintético completo com `FakeLLM` (2 episódios) → `metrics.json` presente → `report --json` com camada 1 e 2 preenchidas.

---

## 12. Critérios de pronto

- Suíte completa passando (testes anteriores + novos), `ruff` limpo.
- `translaterany report <série>` mostra processo por etapa, por modelo, indicadores finais e instantâneos para uma série sintética.
- **Aceite real:** uma temporada de *Charlotte* traduzida com modelos locais; `report --json` gera a primeira linha de base, salva em `docs/baselines/2026-MM-DD-m5-charlotte.json` (apenas números agregados).
- `STATE.md` atualizado.
