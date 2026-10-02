# M8 — Portões e laço do QA · Design

- **Marco:** M8 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-10-01
- **Status:** aprovado pelo usuário (pronto para plano)
- **Depende de:** M0 a M7 ([spec M7](2026-10-01-m7-refinamento-ii-design.md)), com suíte de 583 testes passando na `master`
- **Branch:** `m8-portoes-qa` (a partir de `master`)

---

## 1. Objetivo

Concluir a versão 1.0 (v1) do **TranslaterAny** garantindo a entrega de legendas PT-BR de alta qualidade e totalmente automatizadas, através de um sistema robusto de controle de qualidade em duas camadas:

1. **Portões por etapa (`StageGate`):** validação imediata na saída das etapas de tradução e refinamento, contendo erros críticos na origem e escalonando retentativas de forma inteligente e econômica.
2. **Laço de QA final (`QALoopStage`):** auditoria de ponta a ponta da legenda final antes da gravação em disco, com checagens estruturais exclusivas, rastreamento de causa raiz (*blame*) e reprocessamento focado em cascata apenas para as linhas defeituosas.
3. **Prevenção de regressões e controle de custo:** salvaguardas estritas ("nunca piorar", detecção de oscilação, limites de tentativas e teto de chamadas extras), garantindo que o pipeline sempre termine e nunca gere custos inesperados.

---

## 2. Evidências e Motivação

| Desafio observado nos marcos anteriores | Resposta do M8 |
|---|---|
| Modelos de tradução podem ocasionalmente omitir termos obrigatórios do glossário ou quebrar marcadores `⟦n⟧` durante a primeira geração | O `StageGate` intercepta a saída de `translate_dialogue` e força re-prompt com feedback corretivo antes de propagar a fala |
| Falas com problemas pontuais se beneficiam de isolamento sem a interferência do contexto circundante | A escada de escalonamento reduz o bloco para 1 linha (`batch_size = 1`) na segunda tentativa, eliminando conflitos de ID |
| Trocas constantes de modelos na GPU RTX 3060 12GB causam perda de tempo com recarregamento de pesos na VRAM | O escalonamento no perfil local mantém o mesmo modelo, focando a correção estritamente no prompt e no tamanho do lote |
| Quebras de linha e formatação ASS podem sofrer pequenas inconsistências após a redistribuição de frases | O `QALoopStage` verifica a sintaxe ASS, balanceamento de chaves e coerência de timing contra o arquivo base original |
| Quando uma checagem final falha, não se sabe qual etapa gerou o defeito | O algoritmo de *blame* inspeciona os artefatos históricos do episódio (`UnitTexts`) e aponta a etapa responsável |

---

## 3. Fora do Escopo

| Item | Justificativa / Destino |
|---|---|
| Métricas camada 3 / IA como juiz (COMETKiwi, LLM-as-a-judge) | Backlog pós-v1 (avaliado no roadmap) |
| Troca dinâmica de modelo local pesado na GPU (ex.: carregar modelo 27B) | Evitado no perfil local para prevenir thrashing de VRAM na RTX 3060 de 12 GB |
| Modificação de timing e karaokê de músicas | Músicas são preservadas/intocadas conforme estabelecido no M4 |
| Edição manual de legendas | O processo é 100% automático |

---

## 4. Decisões Acordadas

| # | Decisão | Justificativa |
|---|---|---|
| **D1** | **Abordagem A: `StageGate` acoplado às etapas + `qa_loop` dedicado** | Mantém a simplicidade e pureza do `Runner`, integrando portões nas etapas de IA e o QA como etapa padrão antes de `write`. |
| **D2** | **Apenas erros severos bloqueiam os portões** | `prompt_leak`, marcadores/tags corrompidas (`⟦n⟧` e ASS), 100% não traduzido e termos do glossário violados. Desvios de estilo/CPS ficam para as etapas de refinamento. |
| **D3** | **Escalonamento local em 2 níveis sem troca de GPU** | Nível 1: Feedback no prompt com o erro exato; Nível 2: Redução para bloco unitário (1 fala por chamada). |
| **D4** | **Critério "Nunca Piorar" (Never Worsen)** | Se as tentativas esgotarem ou a versão corrigida introduzir novo erro severo, adota deterministamente a versão candidata com menor severidade. |
| **D5** | **Detecção de Oscilação** | Rastreia os hashes das saídas geradas por ID. Se uma nova versão for idêntica a uma rodada anterior, interrompe o loop naquela unidade. |
| **D6** | **Atribuição de culpa (*Blame*) retroativa** | O `qa_loop` percorre de trás para frente os artefatos históricos do episódio para identificar em qual etapa a falha surgiu. |
| **D7** | **Cascata focada na linha defeituosa** | Apenas a linha defeituosa é reprocessada a partir da etapa culpada e desce pelas etapas posteriores ativas até a redistribuição. |
| **D8** | **Limites rígidos de execução** | Máximo de 2 tentativas por portão, 2 rodadas no QA final e teto configurável de chamadas extras (`max_extra_calls = 30`). |
| **D9** | **Artefato `qa_report.json` e aviso de modelo** | Persistência do relatório de intervenções e emissão de aviso visual se a taxa de edição acumulada ultrapassar 25%. |

---

## 5. Arquitetura e Ordem do Pipeline

### 5.1 Encaixe no `DEFAULT_PIPELINE`
A etapa `qa_loop` é posicionada logo após `redistribute_sentences` e antes de `quality_checks` e `write`:

```
... → colloquial → treatment_consistency → adapt → orthography
    → final_readthrough
    → redistribute_sentences  (gera falas formatadas com quebras \N e timing final)
    → qa_loop                 (M8: auditoria de tags ASS, integridade de eventos, blame e cascata)
    → quality_checks          (medição passiva de indicadores e gravação de metrics.json)
    → write → remux
```

### 5.2 Estrutura do `StageGate`
O `StageGate` envolve as etapas que geram ou refinam diálogos (`TranslateDialogueStage` e subclasses de `DialogueRefineStage`):

```
Entrada da etapa → Chamada LLM Normal (Tentativa 0)
                   ↓
        [Avaliação do StageGate]
                   ↓
   Sem erros severos? → Salva artefato e segue
                   ↓ (se erro severo)
   Tentativa 1: Re-prompt com feedback corretivo pontual
                   ↓
   Tentativa 2: Bloco unitário (1 fala)
                   ↓
   Esgotou/Oscilou? → Aplica 'Nunca Piorar' (melhor versão)
```

---

## 6. Detalhamento dos Componentes

### 6.1 `StageGate` (`src/translaterany/pipeline/gates.py`)
* Recebe a lista de falas geradas, o prompt de entrada e as informações contextuais (glossário, limites).
* Avalia as checagens com a função `run_line_checks`.
* Filtra exclusivamente os achados severos bloqueantes:
  - `prompt_leak`
  - `markers_broken` / `format_mismatch`
  - `untranslated`
  - `glossary_violation`
* Conduz as retentativas incrementando as métricas de chamadas extras no `StageMetrics`.

### 6.2 Checagens Exclusivas Finais do QA (`src/translaterany/checks/final_qa.py`)
Módulo específico para conferência do produto final:
1. `check_ass_syntax`: validação de chaves `{...}`, tags ASS conhecidas, integridade de escapes e ausência de quebras consecutivas inválidas (`\N\N`).
2. `check_event_integrity`: contagem exata de eventos de diálogo contra a faixa original, sem eventos vazios ou com duração zero.
3. `check_timing_bounds`: tempos `start` e `end` válidos, ordenados e sem sobreposições anômalas não presentes na faixa base.

### 6.3 Algoritmo de Blame e Cascata (`src/translaterany/stages/qa_loop.py`)
1. **Auditoria:** Varre os eventos gerados por `redistribute_sentences` com as checagens finais e checagens severas remanescentes.
2. **Blame:** Para cada linha defeituosa, lê os artefatos históricos persistidos na pasta do episódio:
   - `translate_dialogue` → `review_meaning` → `colloquial` → `treatment_consistency` → `adapt` → `orthography` → `final_readthrough`.
   - Compara o texto da unidade em cada etapa. A primeira etapa em que o defeito se manifesta é carimbada como `blamed_stage`.
3. **Cascata:**
   - Prepara uma versão unitária de contexto apenas para a fala culpada.
   - Invoca a etapa causadora com prompt de feedback corretivo.
   - Passa o resultado sequencialmente pelas etapas posteriores habilitadas que possuam `produces_dialogue = True`.
   - Reconstrói o evento redistribuído e revalida.
4. **Proteção:** Máximo de 2 rodadas. Se o erro não for resolvido, mantém a melhor versão e registra no relatório.

### 6.4 Relatório de QA (`qa_report.json`)
Gravado no diretório de artefatos do episódio:
* `rounds_executed`: número de rodadas (1 ou 2).
* `extra_calls_used`: total de chamadas extras de IA gastas no QA.
* `blame_summary`: contagem de culpas por etapa.
* `interventions`: lista detalhada com `unit_id`, `blamed_stage`, `error`, `outcome` (`fixed`, `reverted`, `exhausted`).
* `metrics`: taxa de edição acumulada e achados não resolvidos.

---

## 7. Configuração TOML

Novos blocos em `config.toml` com valores padrão:

```toml
[gates]
enabled = true
max_retries = 2                # Tentativas extras por bloco/linha no portão de etapa

[stages.qa_loop]
enabled = true
max_rounds = 2                 # Máximo de rodadas de auditoria no QA final
max_extra_calls = 30           # Teto de chamadas extras de LLM no episódio
warn_edit_rate_threshold = 0.25 # Alerta se mais de 25% das falas forem editadas no pós-processamento
```

---

## 8. Estratégia de Testes

1. **Testes Unitários de Portão (`tests/test_stage_gate.py`):**
   - Detecção de erros bloqueantes vs. ignorar avisos menores.
   - Escada de escalonamento (feedback e redução unitária).
   - Detecção de oscilação (hash idêntico encerra retentativa).
   - Regra "Nunca Piorar" (não aceitar saída pior).
2. **Testes Unitários de Checagens Finais (`tests/test_final_qa_checks.py`):**
   - Detecção de sintaxe ASS malformada e tags corrompidas.
   - Detecção de integridade de eventos e contagem.
3. **Testes do Laço de QA e Blame (`tests/test_qa_loop.py`):**
   - Rastreamento correto de *blame* através do histórico de artefatos.
   - Cascata de reprocessamento focada na linha.
   - Respeito ao teto de chamadas (`max_extra_calls`) e término garantido.
4. **Teste de Integração do Pipeline (`tests/test_m8_pipeline.py`):**
   - Pipeline completo ponta a ponta com `qa_loop` e `StageGate`.
   - Emissão de `qa_report.json` e exibição de resumo no CLI `report`.

---

## 9. Critérios de Aceite do Marco 8 (Fim da v1)

- [ ] Todas as etapas de diálogo rodam protegidas por `StageGate`.
- [ ] Erros bloqueantes severos disparam retentativa com feedback e bloco unitário.
- [ ] `qa_loop` detecta falhas na legenda redistribuída, identifica a etapa responsável (*blame*) e reprocessa a linha em cascata.
- [ ] Salvaguardas ("nunca piorar", oscilação, orçamentos máximos) garantem que nenhum loop infinito ocorra.
- [ ] `qa_report.json` é gerado para cada episódio com histórico transparente de correções.
- [ ] Suíte completa de testes sintéticos passando 100% verde.
