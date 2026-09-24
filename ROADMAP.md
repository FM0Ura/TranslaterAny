# Roadmap — TranslaterAny

> Tradução automática de legendas de anime (EN → PT-BR) com IA **local-first**, em um pipeline de múltiplas etapas focado em qualidade e fluidez.

O progresso corrente, decisões e pendências ficam em [`STATE.md`](STATE.md).

---

## Como este roadmap funciona

- O projeto é dividido em **marcos** (M0, M1, …). Cada marco tem **o seu próprio spec** em `docs/superpowers/specs/`, seguido de um plano de implementação e só então código.
- Cada marco entrega algo **utilizável e testável sozinho** e tem critérios de "pronto" verificáveis.
- Um marco só começa quando o anterior está pronto. Descobertas durante um marco que afetem os seguintes são registradas em `STATE.md` e refletidas aqui.
- A **v1** está completa ao fim do M8.

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
| **M8** | Portões e laço do QA | Correção automática guiada por métricas, com escalonamento e *blame* |

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

**Pronto quando:** regressões introduzidas por etapas posteriores são detectadas e corrigidas automaticamente em testes; os limites de tentativa e orçamento são respeitados; o `report` mostra o efeito dos portões. **Fim da v1.**

---

## Depois da v1 (backlog)

- `eval` com conjunto de ouro + **métricas camada 3** (COMETKiwi, IA como juiz).
- **Guia de estilo por série** (`style.yaml`) — adiado ("por enquanto não").
- Política configurável para notas de tradução (T/N) do fansub.
- Troca automática para fonte de fallback quando a fonte do fansub não tiver acentos.
- Portões de etapa anterior (retraduzir o episódio quando a taxa de edição da revisão for alta).
- Diarização de áudio para elevar a confiança da atribuição de falantes.
- OCR para legendas em imagem (PGS/VobSub).
- UI web e/ou serviço automático (observar pasta, webhook Sonarr/Jellyfin).

## Descartado

- **Aprender com correções manuais** (`learn`) — descartado pelo usuário.
- **Orquestradores externos** (Prefect, Dagster, LangGraph) — runner próprio atende; reavaliar só se o fluxo passar a ser decidido pela IA.
- **LiteLLM** — preterido em favor de `pydantic-ai-slim`.
