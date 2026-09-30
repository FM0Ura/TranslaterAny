# M6 — Refinamento I · Design

- **Marco:** M6 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-30
- **Status:** aprovado (2026-09-30) · plano: [2026-09-30-m6-refinamento-i.md](../plans/2026-09-30-m6-refinamento-i.md)
- **Depende de:** M4 ([spec](2026-09-27-m4-traducao-contextual-design.md)) e M5 ([spec](2026-09-30-m5-verificacoes-metricas-design.md)), mais as correções de uso real de 2026-09-30 (API nativa do Ollama, uma fala por chamada, análise por cena, legibilidade)
- **Branch:** `m6-refinamento-i` (a partir de `m5-verificacoes-metricas`)

---

## 1. Objetivo

Corrigir **sentido** e dar **naturalidade** às traduções sem reprocessar o episódio inteiro:

1. Protocolo de resposta **só com edições** (`{id, new, reason}`), validado fala a fala;
2. **Triagem** por regras (sem IA) que destaca riscos de sentido e escolhe as falas da coloquialidade;
3. Etapa **`review_meaning`**: revisão de fidelidade de todas as falas, em blocos por cena;
4. Etapa **`colloquial`**: naturalidade PT-BR só nas falas triadas, sem mudar o sentido;
5. **Reversões** entre as duas etapas medidas e bloqueadas.

---

## 2. Evidências do uso real (Charlotte S01E01, 2026-09-30)

| Evidência | Implicação |
|---|---|
| Erros graves **sem sinal de regra**: "…colar em tudo, **seu merda**." (palavrão inventado), "What's this I hear?" → "Que barulho é esse?" | a revisão de sentido lê **todas** as falas; a triagem é destaque, não filtro |
| TranslateGemma é bom tradutor mas ruim com JSON em lote; Gemma4 (sem raciocínio) lida bem com JSON por cena | revisão no papel `review` (Gemma4) |
| Episódio já custa ~22 min (cena ~11, diálogo ~11) | resposta só com edições; coloquialidade só nas triadas |
| TranslateGemma já sai coloquial ("tá bombando") | coloquialidade triada, não em tudo |
| Legibilidade recém-conquistada (8,7% de linhas com problema) | revisão **antes** da redistribuição, para a quebra de linha ser refeita no fim |

---

## 3. Fora do escopo

| Item | Onde |
|---|---|
| Coerência de tratamento (você/tu/senhor) e gênero por par de personagens | M7 |
| Adaptação por velocidade de leitura com IA, ortografia (LanguageTool), leitura corrida final | M7 |
| Portões por etapa, laço do QA, *blame* | M8 |
| Revisão de placas e músicas | não planejado (placas: problema é marcador, não sentido; músicas puladas por padrão) |

---

## 4. Decisões acordadas

| # | Decisão | Origem |
|---|---|---|
| **D1** | `review_meaning` lê **todas** as falas de diálogo em blocos por cena; sinais da triagem entram como destaque no prompt | Usuário |
| **D2** | `colloquial` é **triada** e **ligada por padrão** | Usuário |
| **D3** | **Abordagem B**: as duas etapas atuam sobre **frases inteiras** (ids compostos), **antes** de `redistribute_sentences`; redistribuição e quebra de linha acontecem uma vez, no fim | Usuário |
| **D4** | Toda edição passa por validação local; edição que cria achado novo nas checagens de sentido é rejeitada ("nunca piorar" sem IA) | Design |
| **D5** | Reversão = edição da `colloquial` que devolve uma fala ao texto anterior à `review_meaning`; é rejeitada e contada | Design |
| **D6** | `redistribute_sentences` passa a ler o diálogo da **última etapa com `produces_dialogue`** anterior a ele (via `bind_pipeline`) | Design |
| **D7** | Nova checagem `profanity_added` no pacote `checks` do M5 | Design |
| **D8** | Linha de base pré-M6 salva em `docs/baselines/2026-09-30-m5-charlotte-s01e01.json` | Design |

---

## 5. Pacote `translaterany.refine`

### 5.1 `refine/edits.py` — protocolo só com edições

```python
class LineEdit(BaseModel):
    id: str
    new: str
    reason: str = ""

class EditsResponse(BaseModel):
    edits: list[LineEdit] = Field(default_factory=list)

type RejectReason = Literal["unknown_id", "markers", "empty", "unchanged", "worse", "reversal"]

@dataclass
class EditOutcome:
    texts: dict[str, str]                     # mapa completo após as edições aceitas
    applied: dict[str, str]                   # id -> texto novo
    rejected: dict[RejectReason, int]

def apply_edits(
    texts: Mapping[str, str],                 # mapa atual (todas as falas)
    edits: Iterable[LineEdit],
    targets: set[str],                        # ids editáveis neste bloco
    sources: Mapping[str, LineSource],        # EN, tipo, duração (checks.snapshots)
    env: CheckEnv,
    forbidden: Mapping[str, str] | None = None,  # id -> texto que a edição não pode reproduzir (reversão)
) -> EditOutcome
```

Validação por edição, em ordem:
1. id normalizado (`[u1]` → `u1`); fora de `targets` → `unknown_id`;
2. `new` vazio → `empty`; igual ao atual → `unchanged`;
3. multiconjunto de marcadores `⟦n⟧` ≠ o da fonte → `markers`;
4. `forbidden[id] == new` (espaços normalizados) → `reversal`;
5. **piora**: roda `run_line_checks` com as checagens de sentido (`markers`, `numbers`, `negation`, `names`, `glossary`, `profanity_added`) antes e depois; se surgir `(check)` que não existia antes → `worse`.

Edições duplicadas para o mesmo id: vale a última.

### 5.2 `refine/blocks.py` — blocos por cena

```python
@dataclass
class ReviewLine:
    id: str
    source: str            # EN (frase inteira, sem \N)
    target: str            # PT atual
    speaker: str
    tone: str
    budget: int | None     # orçamento de caracteres (linebreak.char_budget)
    signals: list[str]     # da triagem
    editable: bool         # False = contexto só de leitura

def build_blocks(
    ids: Sequence[str],                        # frases de diálogo em ordem
    targets: set[str],
    scene_of: Mapping[str, int],               # id -> índice de cena
    max_lines: int,
) -> list[list[str]]
```

Agrupa por cena (mesma regra de `scene_analysis._scene_groups`, extraída para uma função compartilhada em `subtitles/scenes.py`) e fatia em blocos de até `max_lines`. Blocos sem nenhum id de `targets` são descartados. Na `colloquial`, as falas não-alvo da mesma cena entram como contexto (`editable=False`).

O prompt é JSON com a lista de `ReviewLine` e instruções fixas; a resposta é `EditsResponse`.

### 5.3 `refine/triage.py` — triagem por regras

```python
MEANING_SIGNALS = {"negation", "numbers", "names", "glossary", "length_ratio", "untranslated", "profanity_added"}

def meaning_signals(lines: Sequence[LineInput], env: CheckEnv) -> dict[str, list[str]]
def colloquial_signals(lines: Sequence[LineInput], speakers_with_style: set[str],
                       speaker_of: Mapping[str, str]) -> dict[str, list[str]]
```

- `meaning_signals`: nomes das checagens de `MEANING_SIGNALS` com achado na linha.
- `colloquial_signals` (léxico em `refine/lexicon.py`):
  - `formal_connective`: "No entanto", "Entretanto", "Contudo", "Todavia", "a fim de", "portanto" (palavra inteira, sem diferenciar caixa);
  - `enclisis`: verbo + `-lo/-la/-los/-las` ou `-se` em início de frase ("fazê-lo", "Encontra-se");
  - `redundant_subject`: início "Eu estou"/"Eu sou"/"Eu vou"/"Eu tenho";
  - `archaic_pronoun`: "tu", "vós", "convosco";
  - `too_long`: `len(PT) > 1.3 × len(EN)` (visíveis) e `len(EN) ≥ 10`;
  - `speech_style`: falante com `speech_style` conhecido em `characters.yaml` (via `scene_analysis`).

### 5.4 Nova checagem `profanity_added` (pacote `checks`)

`warn` quando o PT contém palavra do léxico de palavrões PT (merda, porra, caralho, puta, foda, foder, fodido, cacete, desgraça, arrombado, babaca, idiota, imbecil…) e o EN não contém nenhuma do léxico EN (shit, fuck, damn, bitch, bastard, ass, crap, idiot, moron, jerk, hell…) — palavra inteira, sem diferenciar caixa. Tipos: `dialogue`. Aparece no `report`.

---

## 6. Etapas

Comuns às duas:
- escopo episódio; `produces_texts = True`; **`produces_dialogue = True`** (nova ClassVar em `Stage`, também declarada por `translate_dialogue`);
- `bind_pipeline`: entrada de diálogo = última etapa anterior com `produces_dialogue`; limites (`max_cps`, `max_cpl`) do `[checks]`; `cache_payload` inclui limites e o nome da entrada;
- entradas: `normalize`, `classify`, `merge_sentences`, `scene_analysis`, `consolidate_memory` (se habilitadas antes) e a entrada de diálogo;
- saída: `UnitTexts` com **o mapa completo** de diálogo (mesmas chaves da entrada) e `used_terms` repassado;
- `Options`: `model = "review"`, `max_lines_per_block = 30`;
- falha de bloco (erro de IA ou `EditsResponse` inválido após a nova tentativa do cliente) → bloco passa sem mudanças, `blocks_failed += 1`; o episódio nunca falha por isso.

### 6.1 `review_meaning`

- alvos = todas as frases de diálogo com tradução; sinais de `meaning_signals` como destaque;
- instruções (PT): revisar **só fidelidade** — omissões, acréscimos (inclusive ofensas/palavrões ausentes no original), sentido trocado, gênero/número errado quando o contexto deixa claro; **não reescrever estilo**; respeitar o limite de caracteres; responder só com as falas que precisam mudar.

### 6.2 `colloquial`

- alvos = falas com algum sinal de `colloquial_signals`; cenas sem alvo não geram chamada;
- instruções (PT): mais natural em PT-BR falado, no tom do personagem, **sem mudar o sentido**, sem acrescentar gírias/palavrões ausentes no original, dentro do limite;
- `forbidden` = para cada fala editada pela `review_meaning`, o texto **anterior** a ela (lido do artefato da etapa de diálogo que alimentou a `review_meaning`) → reversão rejeitada.

### 6.3 Contadores (camada 1 do M5)

`lines_read`, `lines_targeted`, `blocks`, `blocks_failed`, `edits_proposed`, `edits_applied`, `rejected_<motivo>` (um por `RejectReason`), `reversals` (só `colloquial`).

---

## 7. Pipeline

```
… scene_analysis → translate_dialogue → translate_signs → translate_songs
  → review_meaning → colloquial → redistribute_sentences → write → publish → remux → quality_checks
```

- `redistribute_sentences`: entrada de diálogo via `bind_pipeline` (D6); versão sobe.
- `quality_checks` descobre as duas etapas como instantâneos (sem mudança de código); o `report` mostra linhas alteradas, achados novos/resolvidos e taxa de edição de cada uma.
- `stages/__init__.py`: registra `review_meaning` e `colloquial` e atualiza `DEFAULT_PIPELINE`.

---

## 8. Estratégia de testes

Sintéticos, `FakeLLM`:

1. `apply_edits`: cada motivo de rejeição (`unknown_id`, `empty`, `unchanged`, `markers`, `reversal`, `worse` por negação sumida e por palavrão acrescentado); id com colchetes; duplicadas.
2. Triagem: cada sinal de sentido e de coloquialidade; `speech_style`.
3. `build_blocks`: agrupamento por cena, fatiamento, descarte de blocos sem alvo; contexto só de leitura.
4. `profanity_added`: casos positivos e negativos (EN com palavrão → não sinaliza).
5. `review_meaning`: aplica edição válida; rejeita inválida com contador; bloco com falha passa inalterado; mapa de saída completo.
6. `colloquial`: só alvos triados; cena sem alvo não chama o modelo; reversão bloqueada e contada.
7. `redistribute_sentences` escolhe a última etapa de diálogo, inclusive com `review_meaning`/`colloquial` desligadas via config.
8. E2E: pipeline padrão completo com as duas etapas; `report` mostra os instantâneos.

---

## 9. Critérios de pronto

- Suíte completa passando; nenhum erro novo de `ruff` nos arquivos tocados.
- **Aceite real** (Charlotte S01E01, modelos locais), comparado com `docs/baselines/2026-09-30-m5-charlotte-s01e01.json` via `report --baseline`:
  - sinais de risco de sentido (negação, números, nomes, glossário, tamanho anômalo) **caem**; `profanity_added` (checagem nova, sem linha de base) é comparado entre o instantâneo `translate_dialogue` e o final do mesmo run;
  - `reading_speed` não piora mais que 2 p.p. em relação à linha de base;
  - tempo por episódio registrado no `STATE.md`;
  - conferência manual dos casos conhecidos ("seu merda", "Que barulho é esse?").
- `STATE.md` atualizado.
