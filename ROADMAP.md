# Roadmap — TranslaterAny

> Tradução automática de legendas de anime (EN → PT-BR) com IA **local-first**, em um pipeline de múltiplas etapas focado em qualidade e fluidez.

O progresso corrente, decisões e pendências ficam em [`STATE.md`](STATE.md).

---

## Como este roadmap funciona

- O projeto é dividido em **marcos** (M0, M1, …). Cada marco tem **o seu próprio spec** em `docs/superpowers/specs/`, seguido de um plano de implementação e só então código.
- Cada marco entrega algo **utilizável e testável sozinho** e tem critérios de "pronto" verificáveis.
- Um marco só começa quando o anterior está pronto. Descobertas durante um marco que afetem os seguintes são registradas em `STATE.md` e refletidas aqui.
- A **v1** está completa ao fim do M8 (versão estável lançada: `v1.0.0`).
- A **v1.1** introduz OCR de legendas em imagem (PGS/VobSub) e suporte universal a qualquer idioma de entrada e saída.
- A **v1.2** introduz Diarização de Áudio e Multimodalidade (Marco M11): extração acústica de vozes, Map-Reduce de perfis de voz por série e fusão multimodal para identificação precisa de falantes e gênero.

---

## Visão

Uma aplicação CLI que percorre uma biblioteca de animes (MKV com legendas EN embutidas), estuda cada série e produz legendas PT-BR com qualidade de fansub competente:

- nomes, termos e tratamento **consistentes** ao longo da série;
- **tom certo** para cada personagem;
- **timing, estilos e efeitos** do `.ass` original preservados;
- linhas **legíveis** na velocidade da tela;
- **totalmente automático**: nenhuma parada para revisão humana; tudo que for editável (glossário, fichas) fica em YAML para correção posterior.

---

## Arquitetura acordada (resumo)

### Duas fases

**Fase 1 — Análise da série** (uma vez por série, antes de traduzir)

| # | Etapa | IA? | Resultado |
|---|---|---|---|
| 1 | Metadados | ❌ | AniList (personagens, nome, gênero, papel, gêneros/tags) + Jikan (sinopse por episódio, via `idMal`) |
| 2 | Extração (map, por episódio) | ✅ | termos, estilos de fala, personagens extras, resumo |
| 3 | Consolidação (reduce, por série) | ✅ | `glossary.yaml`, `characters.yaml`, `story.yaml` |

**Fase 2 — Tradução** (por episódio; runner processa **por etapa** em todos os episódios para minimizar troca de modelo na GPU)

```
extrair → normalizar → classificar → memória de tradução → unir frases
→ análise de cena (falantes + contexto + desafios)
→ traduzir diálogo / placas / músicas → redistribuir
→ revisar sentido* → coloquialidade* → coerência* → adaptar*
→ ortografia (LanguageTool) → leitura corrida final* → QA (laço) → gravar
```
`*` = com triagem e/ou respondendo apenas com edições.

### Princípios

- **Etapas plugáveis:** toda etapa implementa a interface `Stage`; a lista e a ordem vêm da configuração.
- **Roteamento por tipo de linha:** diálogo, placa, música, karaokê, desenho, narração — cada etapa declara os tipos que processa.
- **Artefato por etapa + manifest:** retomada, cache por hash (entrada + config + versão do prompt), invalidação seletiva.
- **Economia de geração:** triagem sem IA decide quais linhas entram em cada etapa; etapas de verificação devolvem só edições; prompts em "prefixo fixo + bloco variável" para cache.
- **Qualidade em duas camadas de controle:** portões por etapa (erro não se espalha) + laço do QA final (integridade do resultado, detecção de regressões com *blame* por etapa).
- **Nunca piorar, nunca perder trabalho:** escrita atômica, fallback para a versão anterior, "fica a melhor versão".
- **Isolamento da IA:** etapas dependem da interface `LLMClient`, nunca da biblioteca diretamente.

### Stack

- **Python 3.14**, gerenciado com `uv`.
- Libs: `pydantic`, `pydantic-ai-slim[openai,google]`, `pysubs2`, `typer`, `httpx`, `tenacity`, `ruamel.yaml`, `spacy` (+ modelo PT), `fonttools`, `charset-normalizer`.
- Sistema: `ffmpeg`/`ffprobe`, `mkvtoolnix`, `Ollama`, `LanguageTool` (serviço local).
- IA: **local-first** (Ollama); nuvem opcional com **Gemini** ou **ChatGPT**. Perfis `local` (padrão), `hibrido`, `nuvem`.
- Orquestração: **runner próprio** (sem Prefect/LangGraph).

---

## Marcos

| Marco | Nome | Entrega em uma frase |
|---|---|---|
| **M0** | Fundação | Runner com etapas plugáveis, artefatos, retomada e CLI esqueleto |
| **M1** | Mídia e legendas | Extrair, entender e regravar a legenda sem perder nada (roundtrip + remux seguro) |
| **M2** | Camada de IA e tradução básica | Primeira legenda PT-BR real, ponta a ponta, com modelos locais ou nuvem |
| **M3** | Memória da série | Tradução consistente usando glossário, fichas e história da série |
| **M4** | Tradução contextual | Falantes, contexto de cena, desafios, placas, músicas, frases partidas, memória de tradução |
| **M5** | Verificações e métricas | Checagens automáticas, métricas por etapa e `report` — linha de base de qualidade |
| **M6** | Refinamento I | Triagem + edições parciais; revisão de sentido e coloquialidade |
| **M7** | Refinamento II | Coerência de tratamento, adaptação, ortografia e leitura corrida final |
| **M8** | Portões e laço do QA | Correção automática guiada por métricas, com escalonamento e *blame* (Fim da v1.0.0) |
| **v1.1** | OCR & Suporte Universal a Idiomas | Extração OCR de PGS/VobSub e tradução entre quaisquer idiomas configuráveis (source_lang → target_lang) |

---

### M0 — Fundação

**Objetivo:** o esqueleto sobre o qual todas as etapas serão plugadas.

**Escopo**
- Estrutura de pacotes (`cli/`, `config/`, `pipeline/`, `stages/`, `llm/`, `memory/`, `media/`, `subtitles/`).
- Configuração em TOML validada com pydantic (erros com indicação clara do problema).
- Interface `Stage` e runner: execução ordenada a partir do config, **por etapa** (todas as unidades passam pela etapa antes da próxima), etapas de escopo `episode` ou `series`, dependências declaradas.
- Armazenamento de artefatos por episódio, `manifest.json`, hash de entrada + config + versão do prompt, invalidação a partir da etapa alterada.
- Escrita atômica, lock por série, retomada.
- Interface `LLMClient` + `FakeLLM` para testes.
- CLI esqueleto: `run`, `status`, `retry --from`, `doctor` (verificações básicas).

**Fora do escopo:** qualquer etapa real, qualquer IA real.

**Pronto quando:** um pipeline de etapas fictícias roda, é interrompido (Ctrl+C) e retoma exatamente de onde parou; alterar a config de uma etapa reexecuta só ela e as seguintes; testes cobrem runner, manifest e invalidação.

---

### M1 — Mídia e legendas

**Objetivo:** tirar a legenda do MKV, entendê-la estruturalmente e devolvê-la sem perder nada.

**Escopo**
- Varredura da biblioteca e identificação série/temporada/episódio (padrão Jellyfin/Sonarr).
- `ffprobe`: listagem de faixas; seleção da faixa EN (Full > Dialogue > SDH; nunca só Signs); verificação de idioma `und`; override por série.
- **Faixas divididas** (`Dialog` + `S&S` separadas): detectar e tratar as duas (estratégia de saída definida no spec do M1); distinguir de `Full` + `S&S` (usar só `Full`); desempate entre várias faixas `Full`.
- Varredura guiada pelos `.mkv` (metadados `.nfo`/thumbs órfãos de upgrades são ignorados).
- Detecção de casos a pular: PGS/VobSub (imagem), PT-BR já existente (`--force`), arquivo ainda baixando, codificação estranha.
- Tipos de linha e roteamento por tipo (cada etapa declara os tipos que processa).
- Etapas **extrair**, **normalizar** (texto ↔ tags, cenas, duplicatas de efeito, comentários) e **classificar** (apenas por regras: `\pos`, `\k`, `\p1`, nome do estilo).
- Etapa **gravar**: `.pt-BR.ass` externo + **remux opcional seguro** (verificação pós-remux, anexos/fontes preservados, espaço livre, troca atômica, nome temporário oculto).
- Invariantes de saída: timing idêntico, tags íntegras, todos os IDs presentes.
- Hash do MKV para detectar release trocada.

**Pronto quando:** com uma etapa "tradução identidade", o `.ass` gravado é **idêntico** ao original; o remux produz MKV válido com a nova faixa e os anexos; testes geram MKVs sintéticos com ffmpeg.

---

### M2 — Camada de IA e tradução básica

**Objetivo:** primeira legenda PT-BR real, ponta a ponta.

**Escopo**
- `LLMClient` sobre `pydantic-ai-slim`: Ollama (OpenAI-compatible), Gemini, ChatGPT.
- Config de provedores → apelidos de modelos → perfis (`local`, `hibrido`, `nuvem`); `num_ctx` por modelo.
- Saída estruturada validada; retry com `tenacity`; conferência de IDs; pedido das linhas faltantes; divisão do bloco ao meio.
- Blocos por limite de tokens com linhas anteriores como contexto; prompt em "prefixo fixo + bloco variável".
- Estimativa de tokens antes de enviar; aviso de estouro de contexto.
- Controle de custo: `estimate`, `max_cost_usd`, custo real no manifest, tabela de preços no config.
- Recusa por filtro de segurança da nuvem → fallback para modelo local.
- `doctor` completo (Ollama no ar, modelos baixados, chaves, ferramentas).
- Etapa **traduzir diálogo** (sem memória da série ainda).

**Pronto quando:** `translaterany run <pasta>` gera `.pt-BR.ass` legível para uma temporada real usando apenas modelos locais; interrupção e retomada funcionam; falhas simuladas (JSON inválido, linhas faltando) são cobertas por testes com `FakeLLM`.

---

### M3 — Memória da série (Fase 1)

**Objetivo:** consistência ao longo da série.

**Escopo**
- Cliente AniList (GraphQL) e Jikan (via `idMal`), com cache e respeito a limites de requisição.
- Casamento série ↔ AniList (título + ano + nº de episódios; **uma pasta com várias temporadas/especiais ↔ várias entradas AniList**; avaliar bases de mapeamento TVDB/TMDB ↔ AniList); `series.toml` com `anilist_id` para correção; seguir sem metadados quando a confiança for baixa.
- Etapas **extração** (map, por episódio, com sinopse Jikan como entrada extra) e **consolidação** (reduce).
- `glossary.yaml`, `characters.yaml`, `story.yaml` com `ruamel.yaml`; precedência `user` > `metadata` > `extracted`; entradas já usadas não mudam.
- Filtragem do glossário **por episódio** (não por bloco) para preservar cache de prefixo.
- Registro das entradas usadas por episódio; `status` marca desatualizados; `retry --stale`; `metadata refresh`.
- Política de categorias (o que se traduz, o que se mantém).
- Tradução do M2 passa a receber glossário, fichas e história.

**Pronto quando:** uma temporada traduzida usa a mesma forma para cada termo do glossário em todos os episódios; editar um termo marca os episódios afetados e `retry --stale` os refaz.

---

### M4 — Tradução contextual

**Objetivo:** a tradução entende quem fala, com quem, em que clima, e trata cada tipo de linha adequadamente.

**Escopo**
- Etapa **memória de tradução**: reuso de traduções idênticas na série (OP/ED, prévias, bordões).
- Etapas **unir frases** (antes) e **redistribuir** (depois da tradução) para frases partidas entre eventos.
- Etapa **análise de cena** combinada: falantes + interlocutor + confiança; clima, relação e formalidade; anotação de desafios (trocadilhos, expressões, referências, honoríficos, onomatopeias) com estratégia. Separável via config.
- Classificação por IA apenas para linhas ambíguas.
- Tradução ciente da confiança do falante (construções neutras quando baixa).
- Etapas **traduzir placas** e **traduzir músicas** (karaokê intocado).
- Políticas globais no config: honoríficos, nível de palavrão.

**Pronto quando:** OP/ED saem idênticas em todos os episódios sem chamar IA; frases partidas saem fluidas e com timing original; placas e músicas são roteadas para suas etapas; testes cobrem roteamento, união/redistribuição e memória de tradução.

---

### M5 — Verificações e métricas

**Objetivo:** medir antes de refinar — criar a linha de base de qualidade.

**Escopo**
- Módulo de **checagens** reutilizável (usado por triagem, métricas, portões e QA): sinais de risco de sentido (número, negação, nome), aderência ao glossário, velocidade de leitura, marcadores de PT-PT/espanhol, linhas não traduzidas, tamanho anômalo, conflitos de gênero/tratamento (spaCy), fontes sem os caracteres usados (fontTools, só aviso).
- **Métricas camada 1** (processo): taxa de triagem, taxa e tamanho de edição, reversões, falhas, tempo, tokens, custo.
- **Métricas camada 2** (indicadores): checagens medidas antes/depois de cada etapa.
- `metrics.json` por episódio; comando `report` por série e por modelo.

**Pronto quando:** `translaterany report` mostra métricas por etapa e indicadores finais para uma temporada traduzida no M4, servindo de linha de base para M6–M8.

---

### M6 — Refinamento I

**Objetivo:** corrigir sentido e dar naturalidade, sem reprocessar o episódio inteiro.

**Escopo**
- Framework de **triagem** por etapa (regras sem IA; linhas fora da triagem viram contexto somente leitura).
- Protocolo de **resposta só com edições** (`{id, novo}`).
- Etapa **revisar sentido** (apenas fidelidade: nada omitido, inventado ou distorcido).
- Etapa **coloquialidade** (naturalidade PT-BR, tom por personagem).
- Métrica de reversões entre as duas etapas.

**Pronto quando:** comparado à linha de base do M5, os sinais de risco de sentido caem; as etapas processam apenas as linhas triadas e geram só edições; o tempo por episódio fica registrado para comparação.

---

### M7 — Refinamento II

**Objetivo:** coerência no episódio inteiro e acabamento de legenda profissional.

**Escopo**
- Etapa **coerência de tratamento**: por par de personagens (você/tu/senhor) e gênero conforme as fichas; checagem automática decide as linhas; IA corrige conflitos.
- Etapa **adaptar**: velocidade de leitura, quebra de linha, tipografia PT-BR; IA só encurta o que estourou.
- Etapa **ortografia**: LanguageTool local via HTTP; correções simples aplicadas, demais viram indicador.
- Etapa **leitura corrida final** (ligada por padrão): lê só o PT, responde só com edições.

**Pronto quando:** conflitos de gênero/tratamento, violações de velocidade de leitura e erros do LanguageTool caem a (quase) zero no `report`, sem aumentar os sinais de risco de sentido.

---

### M8 — Portões e laço do QA

**Objetivo:** correção automática guiada por métricas, sem laços infinitos nem conta surpresa.

**Escopo**
- **Portões por etapa** configuráveis (apenas métricas objetivas e por linha).
- Escada de escalonamento: feedback no prompt → bloco menor → modelo mais forte → aceitar a melhor versão.
- "Nunca piorar", detecção de oscilação, limite de tentativas, orçamento extra por episódio.
- **Laço do QA** no resultado final: *blame* por etapa via artefatos, reprocessamento **só da linha** a partir da etapa responsável, no máximo 2 rodadas, orçamento próprio; não insiste no que o portão já esgotou.
- Checagens exclusivas do final: tags reinseridas, redistribuição, timing no arquivo gravado.
- `qa_report.json`; taxa de edição alta vira **aviso** ("considere trocar o modelo de tradução").

**Pronto quando:** regressões introduzidas por etapas posteriores são detectadas e corrigidas automaticamente em testes; os limites de tentativa e orçamento são respeitados; o `report` mostra o efeito dos portões. **Fim da v1.0.0.**

---

### v1.1 — OCR e Suporte Universal a Idiomas

**Objetivo:** Permitir que o TranslaterAny processe mídias físicas com legendas gráficas (Blu-ray/DVD) e traduza entre quaisquer idiomas de entrada e saída, desacoplando o pipeline da dependência estrita de EN → PT-BR.

**Escopo:**

1. **Inserção de OCR para Legendas em Imagem (PGS / VobSub) — Marco M10 (✅ Concluído)**
   - **Extração gráfica:** Suporte à extração de faixas PGS (`.sup`) e VobSub (`.sub`/`.idx`) via `mkvextract`.
   - **Motor de OCR local:** Integração com motor de OCR leve e determinístico (ex.: Tesseract OCR / `pytesseract` ou PaddleOCR) com suporte a múltiplos idiomas e execução local paralela.
   - **Normalização e alinhamento:** Conversão dos bitmaps e timestamps para texto estruturado (`NormalizedDoc`), preservando tempos exatos de início e fim.
   - **Detecção de estilos e posições:** Inferência de diálogos, quebras de linha e formatações básicas (itálico/posição na tela) a partir dos bounding boxes do OCR.
   - **Fluxo transparente:** Uma vez reconhecidas pelo OCR, as legendas entram diretamente nas etapas existentes (`classify`, `scene_analysis`, `translate`, etc.) sem distinção de legendas textuais normais.

2. **Suporte Universal a Idiomas de Entrada e Saída — Marco M9 (✅ Concluído)**
   - **Configuração dinâmica de pares linguísticos:**
     - `source_language`: idioma de origem configurável globalmente, por série ou CLI (ex.: `ja`, `en`, `es`, `fr`, `de`, `zh`, `ko`, etc. — padrão: `en`).
     - `target_language`: idioma de destino configurável (ex.: `pt-BR`, `es`, `en`, `fr`, `de`, `it`, `ja`, etc. — padrão: `pt-BR`).
   - **Catálogo e resolução universal (`LanguageRegistry`):**
     - Resolução resiliente por códigos ISO e aliases flexíveis; checagem unificada de match com faixas de MKV.
   - **Perfis linguísticos desacoplados (`LanguageProfile`):**
     - `PortugueseProfile` (100% de paridade com o legado PT-BR), `SpanishProfile`, `EnglishProfile` e `GenericProfile` seguro.
   - **Seleção inteligente de faixa:** O seletor de faixas (`select_track`) prioriza o `source_language` e detecta colisões com `target_language`.
   - **Prompts multilíngues parametrizados:**
     - Injeção dinâmica de `{source_language}` e `{target_language}` em todos os templates de prompt (`translate_dialogue`, `translate_signs`, `translate_songs`, `review_meaning`, `final_readthrough`).
   - **LanguageTool parametrizado:**
     - O cliente do LanguageTool envia o código `languagetool_code` correspondente ao `target_language` configurado.
   - **Gravação, publicação e remux adaptados:**
     - Nomenclatura automática do arquivo de legenda com base no idioma de saída: `.{target_language.code}.ass` (ex.: `.pt-BR.ass`, `.es.ass`, `.en.ass`), flags `0:{code}` e nomes legíveis de faixa no remux.

**Pronto quando:**
1. Configurar `source_language = "ja"` ou `target_language = "es"` traduz corretamente os episódios no par linguístico solicitado sem intervenção manual (✅ Concluído no M9);
2. Um MKV contendo apenas faixa PGS/VobSub é processado pelo OCR e gera legendas traduzidas de qualidade comparável a faixas de texto (✅ Concluído no M10);
3. Testes sintéticos e de integração cobrem a extração OCR e a tradução com diferentes pares de idiomas (✅ M9 e M10 concluídos — 715 testes no total).

---

### v1.2 — Diarização de Áudio e Multimodalidade (Marco M11 — ✅ Concluído)

**Objetivo:** Elevar a precisão e confiança da atribuição de falantes (`scene_analysis`) através de análise multimodal de áudio, desambiguando personagens, definindo gênero gramatical canônico/acústico e prevenindo alucinações de gênero e falante.

**Escopo:**

1. **Extração e Embeddings Acústicos (`ExtractVoiceStage` - Map por Episódio):**
   - Extração leve de áudio por fala (`AudioExtractor`) com corte de timestamps exatos via `ffmpeg` (mono, 16kHz, PCM).
   - Motores plugáveis via `DiarizationEngine`:
     - `OnnxAudioDiarizer`: motor local padrão, pesos abertos sem autenticação nem HF token.
     - `PyAnnoteAudioDiarizer`: motor avançado opcional com suporte a `HF_TOKEN` e degradação graciosa se ausente.
   - Diagnósticos no `doctor` para codecs de áudio (`ffmpeg`/`ffprobe`) e runtimes onnx/pyannote.
   - Artefato por episódio: `VoiceEmbeddingsArtifact` (`voice_embeddings.json`).

2. **Consolidação do Banco de Vozes da Série (`ConsolidateVoiceBankStage` - Reduce de Série):**
   - Agrupamento acústico de centróides através de todos os episódios (`VoiceBankDoc` / `voice_bank.json`).
   - Mapeamento determinístico de vozes para o catálogo canônico de personagens (`characters.yaml`).
   - Precedência estrita de gênero: gênero do AniList/metadados sempre tem prioridade sobre o pitch acústico (resolvendo meninos dublados por mulheres).

3. **Fusão Multimodal no Pipeline (`analyze_scenes_multimodal` no `SceneAnalysisStage`):**
   - Associação por similaridade cosseno entre os segmentos de áudio e os perfis do `voice_bank.json`.
   - Confiança elevada para `high` quando o match de voz confirma a hipótese do personagem.
   - Salvaguarda estrita de vocativo: quando um nome de personagem é falado em vocativo na fala, a voz é associada ao interlocutor (*listener*), nunca atribuindo a fala ao personagem chamado.
   - Falantes desconhecidos (`Unknown`): preservam o gênero acústico detectado (`female`/`male`) para manter concordância verbal/nominal correta no PT-BR sem poluir o banco de vozes canônico.
   - Binding dinâmico de pipeline: ativação transparente e condicional das entradas de áudio sem quebrar pipelines parciais ou customizados.

**Pronto quando:**
1. Áudio de cada fala é extraído e embeddado em `voice_embeddings.json` por episódio (✅);
2. `voice_bank.json` agrupa centróides da temporada com perfis de voz consolidados (✅);
3. `scene_analysis` funde áudio + texto elevando confiança para `high` e respeitando salvaguarda de vocativo e precedência de gênero (✅);
4. Suíte completa com 746 testes passando com 100% de sucesso e zero regressões (✅ M11 concluído — 746 testes no total).

---

### Marco M12 — UI Web e API RESTful Desacoplada (v1.3)

**Objetivo:** Interface Web moderna, interativa e desacoplada em 3 camadas, com visualização da biblioteca de animes, fila de processamento em segundo plano com suporte a status PAUSED, retomada e cancelamento, streaming SSE em tempo real, grafo visual de pipeline com nós em bypass e edição das memórias da série.

**Design e Implementação:**
- Servidor ASGI FastAPI desacoplado executável via CLI: `translaterany web [--host 0.0.0.0] [--port 8080]`.
- Camada de API RESTful pura (`/api/v1/`) com endpoints para séries, episódios, memórias, pipeline, jobs e diagnóstico (`doctor`).
- Gerenciador de tarefas (`JobManager`) assíncrono com thread worker dedicada (`max_workers=1` para evitar sobrecarga de GPU), tokens atômicos de pausa/cancelamento cooperativos e broadcaster de eventos SSE (`/api/v1/jobs/{id}/stream`).
- Interface gráfica SSR renderizada com Jinja2, HTMX 2.x e Tailwind CSS embutidos localmente (100% offline, zero dependências Node/npm).
- Grafo visual e interativo de pipeline (DAG com nós e conexões) permitindo ligar e desligar etapas ("Bypass"), tanto globalmente quanto por série (`series.toml`).
- Editor visual de memórias com gerenciamento de personagens (`characters.yaml`), termos de glossário (`glossary.yaml`) e sinopse narrativa (`story.yaml`).
- Inspetor de episódios com comparador de falas e download de arquivos `.pt-BR.ass`.

**Pronto quando:**
1. Servidor ASGI FastAPI inicializado via comando CLI `translaterany web` (✅);
2. API RESTful `/api/v1/` cobre todas as operações de biblioteca, pipeline, configurações e memórias de forma desacoplada (✅);
3. `JobManager` gerencia enfileiramento, pausa atômica entre etapas, cancelamento e streaming de progresso/logs via SSE (✅);
4. Interface gráfica Jinja2 + HTMX funcional e sem dependências externas de rede (✅);
5. Grafo de pipeline interativo reflete nós ativos e bypass por série e globalmente (✅);
6. Suíte completa com 767 testes passando com 100% de sucesso e zero regressões (✅ M12 concluído — 767 testes no total).

---

## Depois da v1.3 (backlog)

- `eval` com conjunto de ouro + **métricas camada 3** (COMETKiwi, IA como juiz).
- **Guia de estilo por série** (`style.yaml`) — adiado ("por enquanto não").
- Política configurável para notas de tradução (T/N) do fansub.
- Troca automática para fonte de fallback quando a fonte do fansub não tiver acentos.
- Portões de etapa anterior (retraduzir o episódio quando a taxa de edição da revisão for alta).
- Observador de diretório em segundo plano / webhook Sonarr/Jellyfin.

## Descartado

- **Aprender com correções manuais** (`learn`) — descartado pelo usuário.
- **Orquestradores externos** (Prefect, Dagster, LangGraph) — runner próprio atende; reavaliar só se o fluxo passar a ser decidido pela IA.
- **LiteLLM** — preterido em favor de `pydantic-ai-slim`.
