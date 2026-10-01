# M7 — Refinamento II · Design

- **Marco:** M7 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-10-01
- **Status:** rascunho (aguardando revisão do usuário)
- **Depende de:** M5 ([spec](2026-09-30-m5-verificacoes-metricas-design.md)) e M6 ([spec](2026-09-30-m6-refinamento-i-design.md)), com a baseline de referência de 4 episódios (`docs/baselines/2026-10-01-m6-charlotte-s01e01-04.json`)
- **Branch:** `m7-refinamento-ii` (a partir de `master`)

---

## 1. Objetivo

Levar as legendas traduzidas a um nível de acabamento profissional de fansub por meio de quatro etapas especializadas de refinamento:

1. **`treatment_consistency`**: unificar pronomes de tratamento (você vs. tu / formalidade) e gênero gramatical entre pares de personagens no episódio, com base no `characters.yaml` e na regra da maioria;
2. **`adapt`**: condensar frases que estouram a velocidade de leitura (CPS > 17), preservando o sentido essencial e sem inventar palavrões;
3. **`orthography`**: revisão ortográfica e gramatical segura via serviço local LanguageTool (HTTP), sem custo de GPU/tokens e com degradação graciosa caso o serviço esteja offline;
4. **`final_readthrough`**: leitura corrida do diálogo 100% em português por cena, lapidando fluidez e transições entre falas, com validação determinística de sentido via `apply_edits`.

---

## 2. Evidências e Motivação

| Evidência dos marcos M5 e M6 | Implicação no M7 |
|---|---|
| A baseline de Charlotte (1.580 falas) registrou 8,7% de falas com problemas de leitura (CPS/CPL) e algumas falas condensadas com sentido trocado | A etapa `adapt` precisa atuar com orçamento estrito de caracteres e prompt focado exclusivamente em concisão sem perda semântica |
| Em legendas longas, o mesmo personagem oscila ocasionalmente entre "você" e "tu" ou flexões de gênero quando a frase original em inglês não marcava gênero | `treatment_consistency` garante que o histórico de falas do par `(falante, interlocutor)` fixe uma postura gramatical estável |
| O modelo TranslateGemma é excelente na tradução direta, mas pequenos erros de digitação e acentuação escapam | O LanguageTool local resolve erros mecânicos de digitação e acentuação de forma determinística e instantânea |
| Avaliar fluidez com o texto original em inglês induz o modelo a reproduzir estruturas sintáticas do inglês (anglicismos) | `final_readthrough` lê exclusivamente o português, mas o validador `apply_edits` verifica o original em inglês nos bastidores |

---

## 3. Fora do Escopo

| Item | Destino / Justificativa |
|---|---|
| Portões de qualidade com reprocessamento automático e blame | Marco 8 (M8 — Portões e laço do QA) |
| Escalação dinâmica de modelos para falas problemáticas | Marco 8 |
| Correção ortográfica de placas e músicas | Fora da v1 (músicas mantêm original/karaokê; placas têm tags estritas) |
| Instalação automática do servidor Docker do LanguageTool | Pré-requisito de ambiente do usuário (o `doctor` apenas verifica e a etapa degrada com elegância) |

---

## 4. Decisões Acordadas

| # | Decisão | Justificativa |
|---|---|---|
| **D1** | **Todas as 4 etapas rodam antes de `redistribute_sentences`** | Operam sobre frases inteiras (`CompositeUnit`), evitando quebrar orações partidas antes do timing final |
| **D2** | **Reutilização estrita do motor `refine/edits.py`** | Resposta das etapas com IA é sempre `edits: list[LineEdit]`, e todas passam pela validação `apply_edits` |
| **D3** | **Degradação graciosa no LanguageTool** | Se o servidor HTTP estiver offline ou em timeout, emite aviso/métrica e pula sem abortar o pipeline |
| **D4** | **Regra da maioria para tratamento de personagens** | Se `characters.yaml` não especificar explicitamente o pronome do personagem, a maioria (>50%) das ocorrências no episódio define o padrão |
| **D5** | **Filtro rigoroso contra falso-positivo no LanguageTool** | Termos de `glossary.yaml`, nomes de `characters.yaml` e regras de estilo/coloquialismo são ignorados |
| **D6** | **`final_readthrough` recebe apenas PT-BR no prompt** | Garante leitura natural de falante nativo; a fidelidade contra a fonte em inglês é assegurada pelo validador |

---

## 5. Arquitetura e Ordem do Pipeline

### 5.1 Fluxo Sequencial

```
... → translate_dialogue → review_meaning → colloquial
    → treatment_consistency  (M7: etapa 1)
    → adapt                  (M7: etapa 2)
    → orthography            (M7: etapa 3)
    → final_readthrough      (M7: etapa 4)
    → redistribute_sentences (quebra em eventos ASS e wrapping CPL)
    → quality_checks → write → remux
```

### 5.2 Ligação Dinâmica (`bind_pipeline`)
`redistribute_sentences` já está configurado para ler o diálogo da última etapa com `produces_dialogue = True`. Com a introdução do M7, ele passará a consumir automaticamente a saída de `final_readthrough` (ou da última etapa ativa anterior).

---

## 6. Detalhamento das Etapas

### 6.1 `treatment_consistency` (Coerência de Tratamento)
* **Objetivo:** Uniformizar pronomes e flexões entre pares `(speaker, interlocutor)` confiáveis ($\text{confiança} \ge 0.7$ no `scene_analysis`).
* **Triagem Determinística:**
  1. Varre todas as falas do episódio agrupadas por par de personagens.
  2. Identifica pronomes e verbos de 2ª vs. 3ª pessoa ("tu/te/teu" vs. "você/lhe/seu/sua").
  3. Identifica adjetivos e particípios predicativos referentes ao falante e interlocutor, checando contra o gênero em `characters.yaml`.
  4. Determina a convenção majoritária do par no episódio.
  5. Se houver divergências, seleciona apenas as falas divergentes como alvos editáveis.
* **Execução da IA:**
  * Se não houver divergências: 0 chamadas à IA.
  * Se houver divergências: envia o bloco da cena com a fala alvo e instrui o modelo (papel `review`, Gemma4) a ajustar a flexão e os pronomes para o padrão adotado.
  * Resposta: `edits: list[LineEdit]`.

### 6.2 `adapt` (Adaptação para Velocidade de Leitura / CPS)
* **Objetivo:** Reduzir o CPS de falas que ultrapassam a velocidade máxima permitida ($\text{CPS} > 17$).
* **Triagem Determinística:**
  * Para cada unidade: $\text{orçamento} = \lfloor \text{max\_cps} \times (\text{duração\_ms} / 1000) \rfloor$.
  * Falas com $\text{CPS} \le 17$ passam direto sem IA.
  * Falas com $\text{CPS} > 17$ tornam-se alvos editáveis.
* **Execução da IA:**
  * Envia as falas estouradas em blocos de cena, informando o orçamento estrito de caracteres para cada uma.
  * Prompt: *"Encurte a fala indicada para caber no limite estrito de caracteres. Preserve o sentido essencial e o tom. NUNCA adicione palavrões ou ofensas não presentes no original ao condensar."*
* **Validação:**
  * Rejeita edições que não reduzirem o comprimento da string ou que violem marcadores inline `⟦n⟧` e checagens de sentido.

### 6.3 `orthography` (LanguageTool)
* **Objetivo:** Correção mecânica e gramatical determinística via HTTP sem IA.
* **Cliente HTTP:**
  * `POST http://localhost:8010/v2/check` com `language=pt-BR&text=...`.
  * Timeout configurável (padrão 5.0 s).
* **Filtros e Regras:**
  * Isenção: qualquer erro em substring contida em `glossary.yaml`, `characters.yaml` ou honoríficos japoneses é descartado.
  * Categorias aplicadas: `TYPOS`, `CASING`, `GRAMMAR` evidente.
  * Categorias bloqueadas: `STYLE`, `COLLOQUIALISMS` (preserva "pra", "tá", "né", contrações orais).
* **Degradação Graciosa:**
  * Em caso de falha de conexão (`httpx.ConnectError`, `httpx.TimeoutException`), registra `orthography_skipped = true` no manifest, emite aviso ao usuário e prossegue sem lançar exceção.

### 6.4 `final_readthrough` (Leitura Corrida Final)
* **Objetivo:** Leitura contínua em português para ajuste de ritmo, fluidez e transição natural entre réplicas.
* **Execução da IA:**
  * O prompt apresenta a sequência de falas da cena em blocos de até 40 falas, contendo apenas o texto em PT-BR e o nome do falante.
  * Papel do modelo: editor de diálogos nativo.
  * Resposta: `edits: list[LineEdit]`.
* **Validação via `apply_edits`:**
  * A edição proposta é comparada contra o texto em inglês da linha original para validar que números, negações, termos canônicos e tags `⟦n⟧` permanecem idênticos.
  * Rejeita qualquer piora semântica (`worse`) ou reversão de termos corrigidos em etapas anteriores (`reversal`).

---

## 7. Configuração (`config.toml`)

```toml
[stages.treatment_consistency]
enabled = true

[stages.adapt]
enabled = true
max_cps = 17.0

[stages.orthography]
enabled = true
url = "http://localhost:8010/v2/check"
timeout_s = 5.0
language = "pt-BR"

[stages.final_readthrough]
enabled = true
```

---

## 8. Métricas e Comando `report`

O comando `translaterany report` incluirá:
* `treatment_consistency`: falas inconsistentes detectadas, edições propostas e aceitas;
* `adapt`: total de falas condensadas, CPS antes vs. depois e taxa de sucesso no enquadramento ao CPS;
* `orthography`: total de correções ortográficas aplicadas, termos isentos ignorados e status do serviço;
* `final_readthrough`: total de lapidações aplicadas e edições rejeitadas por segurança.

---

## 9. Estratégia de Testes

1. `tests/test_stage_treatment_consistency.py`: detecção de maioria pronominal, concordância de gênero e geração de edições.
2. `tests/test_stage_adapt.py`: cálculo de orçamento, filtragem de CPS e encurtamento validado.
3. `tests/test_stage_orthography.py`: cliente HTTP com `respx`, filtros de categorias, isenções de termos de anime e degradação graciosa quando offline.
4. `tests/test_stage_final_readthrough.py`: leitura em blocos de cena em PT-BR e bloqueio de edições que alterem sentido em relação ao original EN.
5. `tests/test_m7_pipeline.py`: teste E2E com `FakeLLM` garantindo a passagem correta dos artefatos entre as 4 novas etapas e entrega final para `redistribute_sentences`.
