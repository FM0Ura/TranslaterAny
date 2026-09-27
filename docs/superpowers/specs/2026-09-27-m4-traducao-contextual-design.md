# M4 — Tradução contextual · Design

- **Marco:** M4 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-27
- **Status:** proposto (2026-09-27) · plano: pendente
- **Depende de:** M0 ([spec](2026-09-24-m0-fundacao-design.md)), M1 ([spec](2026-09-24-m1-midia-legendas-design.md)), M2 ([spec](2026-09-26-m2-camada-ia-traducao-design.md)) e M3 ([spec](2026-09-26-m3-memoria-serie-design.md))

---

## 1. Objetivo

Evoluir a camada de tradução do TranslaterAny para um modelo **plenamente contextual e estilístico**, no qual o sistema:
1. Compreende quem fala, com quem fala, o clima emocional da cena e a relação entre personagens;
2. Conhece e aplica as políticas globais do projeto para **honoríficos japoneses** e **intensidade de palavrões**;
3. Reutiliza traduções exatas de linhas recorrentes em toda a série (músicas de abertura/encerramento, prévias de episódios, placas de título e bordões) através de uma **Memória de Tradução** persistida e editável em YAML, economizando chamadas de IA e garantindo 100% de consistência;
4. Une frases de diálogo partidas entre eventos consecutivos no `.ass` para tradução como sentenças completas e fluidas, redistribuindo-as proporcionalmente nos eventos originais sem alterar o timing do `.ass`;
5. Roteia e traduz **placas (`sign`)** com concisão visual e **músicas (`song`)** com sensibilidade poética (mantendo tags de karaokê e romaji estritamente intocados);
6. Desambigua por IA linhas com classificação incerta remanescentes da etapa de regras.

---

## 2. Fora do escopo

| Item | Onde |
|---|---|
| Métricas de CPS (caracteres por segundo), comprimento e comando `report` | M5 |
| Framework de triagem e protocolo de resposta só com edições | M6 |
| Revisão dedicada de sentido e ajuste de coloquialidade | M6 |
| Coerência formal de pronomes (tu vs você) e integração com LanguageTool | M7 |
| Leitura corrida final | M7 |
| Portões de qualidade configuráveis e laço fechado de QA com blame | M8 |

---

## 3. Evidências do ambiente e modelos

| Item | Característica | Implicação |
|---|---|---|
| **Modelos Locais** | `translategemma:12b` (tradução) e `gemma4:12b` (revisão/análise) no Ollama local. | `translategemma` opera nas etapas de tradução (`dialogue`, `signs`, `songs`). `gemma4` opera nas análises (`scene_analysis` e desambiguação de `classify`). |
| **Economia de GPU** | Geração de texto em GPU local de 12 GB é o gargalo de tempo. | A memória de tradução (TM) corta totalmente chamadas de IA para linhas idênticas (OP/ED somam ~30 a 50 falas por episódio que passam a ter custo zero a partir do ep. 2). |
| **Estrutura ASS** | Linhas de karaokê possuem tags `\k`, `\kf`, `\ko`; estilos romaji contêm `romaji`, `ro`, `rom`. | Karaokê e romaji são estritamente preservados sem tradução. Placas possuem `\pos`, `\move`, `\an` e exigem síntese concisa. |
| **Isolamento de Testes** | Sandbox do ambiente bloqueia conexões de rede TCP. | Testes da suíte `pytest` continuam 100% sintéticos e usam `FakeLLM`. |

---

## 4. Decisões acordadas

| # | Decisão | Origem |
|---|---|---|
| **D1** | **Política padrão de honoríficos (`keep`):** Preservar os honoríficos japoneses romanizados na fala (`-san`, `-kun`, `-chan`, `-senpai`, `sensei`, `-sama`, etc.). Configurável globalmente em `config.toml` e localmente em `series.toml`. | Usuário / Alinhamento |
| **D2** | **Política padrão de palavrões (`faithful`):** Traduzir com fidelidade de tom e peso emocional equivalente ao inglês original, sem censura arbitrária e sem vulgarização desnecessária. Configurável via `config.toml` e `series.toml`. | Usuário / Alinhamento |
| **D3** | **Memória de tradução em YAML por série (`translation_memory.yaml`):** Persistência na pasta da série (`memory/translation_memory.yaml`). Registra correspondências exatas com precedência `user > auto`. Linhas curtas de diálogo monossilábico não entram automaticamente para evitar falsos positivos fora de contexto. | Usuário / Arquitetura |
| **D4** | **União por critérios determinísticos e redistribuição proporcional inteligente:** Unir falas com gap $\le 1500$ ms com reticências, sem pontuação terminal ou início em minúscula. Na volta, dividir a frase PT-BR proporcionalmente à duração dos eventos originais, quebrando preferencialmente em vírgulas/pontuações ou limites de palavras, sem chamada extra de IA. | Usuário / Arquitetura |
| **D5** | **Etapas dedicadas para placas (`translate_signs`) e músicas (`translate_songs`):** Prompts e opções especializados; karaokê (`\k`) e romaji intocados. | Usuário / Arquitetura |
| **D6** | **Desambiguação na etapa `classify` (`ai_disambiguate: bool = True`):** Apenas unidades com `uncertain=True` são enviadas ao LLM para classificação entre diálogo, placa ou música. | Usuário / Arquitetura |
| **D7** | **Tradução ciente da confiança do falante:** Quando a análise de cena tiver confiança alta e personagem conhecido em `characters.yaml`, usa o gênero e estilo do personagem; quando a confiança for baixa ou o falante for desconhecido/multidão, instrui a IA a adotar construções gramaticais neutras em PT-BR. | Roadmap / Design |
| **D8** | **Pipeline Composto (Abordagem A):** Cada transformação é uma etapa modular e inspecionável com artefato próprio; a etapa `redistribute_sentences` consolida o `UnitTexts` final para a etapa `write`. | Usuário / Arquitetura |

---

## 5. Configuração e Políticas Globais

### 5.1 Atualização de `AppConfig` (`config.toml`)

Adição da seção `[translation]` e configurações específicas por etapa:

```toml
[translation]
honorifics = "keep"       # "keep" (padrão), "adapt", "remove"
profanity = "faithful"     # "faithful" (padrão), "soften", "raw"

[stages.classify.options]
ai_disambiguate = true     # Chama IA para desambiguar unidades com uncertain=True
scene_gap_ms = 5000

[stages.translation_memory.options]
enabled = true
min_dialogue_chars = 15    # Diálogos automáticos só são reaproveitados se tiverem >= 15 caracteres

[stages.merge_sentences.options]
max_gap_ms = 1500          # Limite de silêncio entre eventos para união de frase

[stages.scene_analysis.options]
model = "review"           # Modelo analítico (ex.: gemma4)

[stages.translate_dialogue.options]
model = "translate"        # translategemma
fallback_model = "translategemma"
max_tokens_per_batch = 800
max_context_lines = 5

[stages.translate_signs.options]
model = "translate"

[stages.translate_songs.options]
model = "translate"

[stages.redistribute_sentences.options]
auto_feed_tm = true        # Alimenta translation_memory.yaml com novas canções/placas traduzidas
```

---

## 6. Arquitetura e Modelagem de Dados

### 6.1 Desambiguação na Classificação (`ClassifyStage`)
- **Inputs:** `("normalize",)`
- **Fluxo:**
  1. Executa a classificação determinística por regras de estilo e tags ASS (M1);
  2. Se `options.ai_disambiguate == True` e houver unidades com `uncertain=True`:
     - Monta lote com as unidades incertas (estilo, texto limpo, tags ASS e 1 linha anterior/posterior de contexto);
     - Envia ao modelo com schema `DisambiguateOutput`:
       ```python
       class DisambiguatedUnit(BaseModel):
           id: str
           line_type: Literal["dialogue", "sign", "song"]
           reason: str
       ```
     - Atualiza as unidades no `Classification` com `uncertain=False` e `rule="ai_disambiguate"`;
  3. Grava o artefato `classify.json`.

### 6.2 Memória de Tradução (`translaterany.memory.tm` & `TranslationMemoryStage`)
- **Arquivo:** `<data_dir>/series/<series_key>/memory/translation_memory.yaml`
- **Schema Pydantic:**
  ```python
  class TMEntrySource(StrEnum):
      USER = "user"
      AUTO = "auto"

  class TMEntry(BaseModel):
      clean_text: str
      translation: str
      category: Literal["dialogue", "sign", "song"]
      source: TMEntrySource = TMEntrySource.AUTO
      occurrences: int = 1
      episodes: list[str] = Field(default_factory=list)

  class TranslationMemoryDoc(BaseModel):
      entries: dict[str, TMEntry] = Field(default_factory=dict)
  ```
- **Precedência:** `user > auto`. Edições manuais feitas no YAML nunca são sobrescritas.
- **Etapa `TranslationMemoryStage`:**
  - **Inputs:** `("normalize", "classify")`
  - Varre as unidades do episódio.
  - Para `song` e `sign`: correspondência exata de `clean_text` busca tradução imediatamente na TM.
  - Para `dialogue`: correspondência exata busca na TM se `source == "user"` ou se $\text{len}(clean\_text) \ge \text{min\_dialogue\_chars}$.
  - Produz artefato `translation_memory.json` com `matched_units: dict[str, str]` (com os marcadores `⟦n⟧` corretos da unidade).

### 6.3 Fusão e Redistribuição de Frases (`merge_sentences` e `redistribute_sentences`)
- **Modelos:**
  ```python
  class CompositeUnit(BaseModel):
      composite_id: str               # ex.: "u1+u2"
      unit_ids: list[str]             # ["u1", "u2"]
      durations_ms: list[int]         # [1200, 2400]
      clean_text: str                 # "Texto unificado em inglês..."
      text_with_markers: str          # "Texto unificado com ⟦1⟧..."
      speaker: str | None = None

  class MergedUnitsDoc(BaseModel):
      units: list[CompositeUnit]
      merged_count: int
  ```
- **Etapa `MergeSentencesStage`:**
  - **Inputs:** `("normalize", "classify", "translation_memory")`
  - Filtra unidades `dialogue` não resolvidas pela TM.
  - Agrupa $u_i$ e $u_{i+1}$ se:
    - Intervalo $\le \text{max\_gap\_ms}$ (1500 ms);
    - $u_i$ termina em `...`, `…`, `,`, `-`, `--` ou sem pontuação final, OU $u_{i+1}$ começa com minúscula ou `...`.
  - Produz `merge_sentences.json`.
- **Etapa `RedistributeSentencesStage`:**
  - **Inputs:** `("normalize", "classify", "translation_memory", "merge_sentences", "translate_dialogue", "translate_signs", "translate_songs")`
  - Reúne todas as traduções.
  - Para unidades compostas: calcula razão de caracteres $\text{ratio} = \frac{\text{dur}_1}{\text{dur}_{\text{total}}}$, encontra quebra natural próxima (pontuação ou espaço) e distribui os textos para os IDs originais com seus marcadores.
  - Alimenta `translation_memory.yaml` com novas traduções de músicas e placas.
  - Grava o artefato final `UnitTexts` em `redistribute_sentences.json`.

### 6.4 Análise Contextual de Cena (`SceneAnalysisStage`)
- **Inputs:** `("normalize", "classify", "consolidate_memory", "merge_sentences")`
- **Modelos:**
  ```python
  class LineContext(BaseModel):
      speaker: str = "Unknown"
      listener: str = "Unknown"
      confidence: Literal["high", "medium", "low"] = "low"
      tone: str = "neutral"
      relationship: str = ""
      challenges: list[str] = Field(default_factory=list)

  class SceneAnalysisDoc(BaseModel):
      lines: dict[str, LineContext] = Field(default_factory=dict)
  ```
- **Prompt:** Envia bloco da cena com personagens de `characters.yaml` e sinopses de `story.yaml`. Em caso de erro, preenche fallback com `confidence = "low"`.

### 6.5 Etapas de Tradução Especializadas

#### `TranslateDialogueStage`
- **Inputs:** `("normalize", "classify", "consolidate_memory", "translation_memory", "merge_sentences", "scene_analysis")`
- Traduz apenas unidades de diálogo que não estão na TM.
- Injeta no prompt:
  - Contexto de cena: falante, ouvinte, confiança, tom, desafios.
  - Se `confidence == "low"`: regra explícita para usar **construções neutras de gênero**.
  - Política de honoríficos (`honorifics = "keep"`: manter `-san`, `-kun`, `-chan`, etc.).
  - Política de palavrões (`profanity = "faithful"`: peso emocional equivalente sem censura nem acréscimos).
  - Glossário filtrado por episódio (M3).

#### `TranslateSignsStage`
- **Inputs:** `("normalize", "classify", "translation_memory")`
- Traduz unidades `sign` fora da TM.
- Prompt focado em concisão, brevidade e impacto visual. Preserva marcadores de posicionamento e quebra `\N`.

#### `TranslateSongsStage`
- **Inputs:** `("normalize", "classify", "translation_memory")`
- Traduz unidades `song` fora da TM.
- Linhas com tags `\k` (karaokê) ou estilo `romaji` são mantidas inalteradas.
- Prompt focado em poesia, ritmo e naturalidade lírica.

---

## 7. Pipeline Completo no Marco 4

```
inventory
  ↓
metadata (AniList / Jikan)
  ↓
select_track
  ↓
extract
  ↓
normalize
  ↓
classify (com desambiguação por IA opcional)
  ↓
extract_terms (IA por episódio)
  ↓
consolidate_memory (IA por série)
  ↓
translation_memory (reuso exato de linhas da série)
  ↓
merge_sentences (fusão de frases partidas)
  ↓
scene_analysis (falantes, ouvintes, tom, desafios)
  ↓
translate_dialogue + translate_signs + translate_songs (especializadas)
  ↓
redistribute_sentences (divisão proporcional + consolidação + gravação na TM)
  ↓
write (text_source = "redistribute_sentences")
  ↓
publish
  ↓
remux (opcional)
```

---

## 8. Tratamento de Erros e Resiliência

1. **Princípio "Nunca piorar, nunca travar":** Se uma chamada de IA falhar em uma etapa (`scene_analysis`, `translate_dialogue`, `translate_signs`, `translate_songs`), a unidade individual reverte para o texto original ou fallback neutro; o episódio nunca é abortado por uma linha isolada.
2. **Corrupção de TM:** Se `translation_memory.yaml` estiver inválido, a execução opera com memória vazia e emite um aviso no log sem apagar o arquivo do usuário.
3. **Preservação de Marcadores:** Qualquer unidade traduzida que perder ou corromper marcadores inline (`⟦1⟧`, etc.) é automaticamente descartada em favor do texto original em inglês.
4. **Escrita Atômica:** Atualizações na memória de tradução e nos arquivos de legenda utilizam arquivos temporários com rename atômico.

---

## 9. Estratégia de Testes

1. `test_classify_ai.py`: Teste de desambiguação com `FakeLLM` e preservação das regras determinísticas.
2. `test_translation_memory.py`: Carregamento, persistência YAML com comentários, precedência `user > auto`, reuso de músicas/placas e proteção contra diálogos curtos.
3. `test_merge_sentences.py`: Fusão por reticências, minúsculas e pontuação; respeito ao gap temporal `max_gap_ms`; integridade de marcadores.
4. `test_scene_analysis.py`: Atribuição de falantes a partir de `characters.yaml`; pontuação de confiança; fallback em falha de IA.
5. `test_translate_dialogue_contextual.py`: Tradução de diálogo validando honoríficos (`keep`), palavrões (`faithful`), gênero neutro em baixa confiança e termos do glossário.
6. `test_translate_signs_songs.py`: Concisão de placas, tradução lírica de canções e isolamento intocado de `\k` (karaokê) e `romaji`.
7. `test_redistribute_sentences.py`: Divisão proporcional de frases compostas em pontuações e limites de palavras; posicionamento correto de tags ASS.
8. `test_m4_e2e.py`: Teste ponta a ponta em 2 episódios com o pipeline completo, verificando que o Episódio 2 reutiliza a abertura traduzida do Episódio 1 com 0 chamadas de IA na etapa de música.
