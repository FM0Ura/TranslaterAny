# Estado do projeto — TranslaterAny

> Fotografia atual do desenvolvimento. O plano completo está em [`ROADMAP.md`](ROADMAP.md).
> Atualize este arquivo ao concluir cada etapa de um marco (spec, plano, implementação) e sempre que uma decisão for tomada.

**Última atualização:** 2026-10-05

---

## Onde estamos

- **Fase:** v1.1 concluída — **Marco M10 (OCR de Legendas Gráficas PGS/VobSub) concluído com sucesso** (713 testes passando, zero regressões).
- **Marco atual:** **v1.1 finalizada** (M9: Suporte Universal a Idiomas + M10: OCR de Legendas Gráficas).
- **Próxima ação:** Release da v1.1 e planejamento do backlog pós-v1.1.

## Progresso dos marcos

Legenda: ⬜ não iniciado · 📝 spec · 📋 plano · 🔨 implementação · ✅ pronto

| Marco | Status | Spec | Plano | Observações |
|---|---|---|---|---|
| M0 — Fundação | ✅ | [spec](docs/superpowers/specs/2026-09-24-m0-fundacao-design.md) | [plano](docs/superpowers/plans/2026-09-24-m0-fundacao.md) | concluído (101 testes) |
| M1 — Mídia e legendas | ✅ | [spec](docs/superpowers/specs/2026-09-24-m1-midia-legendas-design.md) | [plano](docs/superpowers/plans/2026-09-24-m1-midia-legendas.md) | concluído (237 testes) |
| M2 — Camada de IA e tradução básica | ✅ | [spec](docs/superpowers/specs/2026-09-26-m2-camada-ia-traducao-design.md) | [plano](docs/superpowers/plans/2026-09-26-m2-camada-ia-traducao.md) | concluído (289 testes) |
| M3 — Memória da série | ✅ | [spec](docs/superpowers/specs/2026-09-26-m3-memoria-serie-design.md) | [plano](docs/superpowers/plans/2026-09-26-m3-memoria-serie.md) | concluído (374 testes) |
| M4 — Tradução contextual | ✅ | [spec](docs/superpowers/specs/2026-09-27-m4-traducao-contextual-design.md) | [plano](docs/superpowers/plans/2026-09-27-m4-traducao-contextual.md) | concluído (396 testes) |
| M5 — Verificações e métricas | ✅ | [spec](docs/superpowers/specs/2026-09-30-m5-verificacoes-metricas-design.md) | [plano](docs/superpowers/plans/2026-09-30-m5-verificacoes-metricas.md) | integrado ao master (510 testes); baseline concluída |
| M6 — Refinamento I | ✅ | [spec](docs/superpowers/specs/2026-09-30-m6-refinamento-i-design.md) | [plano](docs/superpowers/plans/2026-09-30-m6-refinamento-i.md) | integrado ao master; aceite real feito — 558 testes |
| M7 — Refinamento II | ✅ | [spec](docs/superpowers/specs/2026-10-01-m7-refinamento-ii-design.md) | [plano](docs/superpowers/plans/2026-10-01-m7-refinamento-ii.md) | integrado ao master (583 testes); LanguageTool e gênero |
| M8 — Portões e laço do QA | ✅ | [spec](docs/superpowers/specs/2026-10-01-m8-portoes-qa-design.md) | [plano](docs/superpowers/plans/2026-10-01-m8-portoes-qa.md) | concluído (659 testes); release v1.0.0 |
| M9 — Suporte Universal a Idiomas (v1.1) | ✅ | [spec](docs/superpowers/specs/2026-10-04-m9-suporte-universal-idiomas-design.md) | [plano](docs/superpowers/plans/2026-10-04-m9-suporte-universal-idiomas.md) | concluído (686 testes); pares arbitrários de idiomas, LanguageRegistry, perfis linguísticos e prompts parametrizados |
| M10 — OCR de Legendas Gráficas (v1.1) | ✅ | [spec](docs/superpowers/specs/2026-10-05-m10-ocr-legendas-graficas-design.md) | [plano](docs/superpowers/plans/2026-10-05-m10-ocr-legendas-graficas.md) | concluído (713 testes); suporte nativo a PGS/VobSub via Tesseract OCR em paralelo, hOCR com itálico, deduplicação SHA-256 e estilos de posição |

---

## Registro de decisões

| Data | Decisão | Motivo / observação |
|---|---|---|
| 2026-09-24 | Abordagem: pipeline linear de etapas especializadas com artefatos persistidos | previsível, retomável, testável por etapa |
| 2026-09-24 | Entrada: legendas **embutidas no MKV** | formato predominante da biblioteca |
| 2026-09-24 | Saída: `.pt-BR.ass` externo por padrão; remux no MKV opcional | não mexe no original; remux quando desejado |
| 2026-09-24 | Provedor de IA configurável **por etapa**; **local-first** (Ollama); nuvem = Gemini ou ChatGPT | custo baixo, GPU RTX 3060 12 GB disponível |
| 2026-09-24 | Interface: **CLI primeiro**; core desacoplado para UI/daemon futuros | |
| 2026-09-24 | **Totalmente automático** — sem paradas para revisão humana | YAMLs continuam editáveis depois |
| 2026-09-24 | **Python 3.14** mantido | |
| 2026-09-24 | Máxima modularidade: etapas plugáveis via config | |
| 2026-09-24 | Memória da série construída sobre a **série inteira** (map-reduce), sem snapshots por episódio | consistência desde o ep. 1; risco de "spoiler" aceito |
| 2026-09-24 | Personagens (nome, gênero, papel) vêm do **AniList**; IA extrai só estilo de fala e personagens ausentes | gênero determinístico |
| 2026-09-24 | Sinopse por episódio via **Jikan** (usando `idMal` do AniList), como entrada extra da extração | sem chave de API |
| 2026-09-24 | Termos do glossário: extração por IA nas legendas | AniList não fornece termos |
| 2026-09-24 | Atribuição de falantes por IA com confiança; tradução neutra quando confiança baixa; diarização de áudio fora da v1 | |
| 2026-09-24 | Sem lib de orquestração (Prefect/LangGraph); **runner próprio** + `tenacity` | fluxo decidido por regras, não pela IA |
| 2026-09-24 | Camada de IA: **`pydantic-ai-slim`** (não LiteLLM), atrás da interface `LLMClient` | saída estruturada validada com retry; suporte oficial a 3.14 |
| 2026-09-24 | Runner processa **por etapa** (todos os episódios) | evita troca de modelo na GPU |
| 2026-09-24 | Revisão de sentido separada da **coloquialidade** (etapa própria) | pedido do usuário: revisor foca só em sentido |
| 2026-09-24 | Roteamento por tipo de linha + novas etapas: classificar, análise de cena combinada, placas, músicas, coerência de tratamento, tipografia, ortografia (LanguageTool) | |
| 2026-09-24 | Desempenho: respostas só com edições, triagem sem IA, análises combinadas, prefixo fixo para cache | saída (geração) é o gargalo em GPU local |
| 2026-09-24 | Glossário filtrado **por episódio**, não por bloco | preserva cache de prefixo |
| 2026-09-24 | Novas etapas aceitas: **memória de tradução**, **unir/redistribuir frases**, **leitura corrida final (ligada por padrão)** | |
| 2026-09-24 | Recusadas: **guia de estilo por série** (por enquanto), **aprender com correções** | honoríficos e palavrão viram config global |
| 2026-09-24 | `eval` e métricas camada 3 ficam para depois da v1; camadas 1 e 2 na v1 | |
| 2026-09-24 | **Portões por etapa + laço do QA final** (ambos), com escalonamento, "nunca piorar", oscilação, orçamentos e *blame* | portões evitam propagação; QA pega regressões e problemas do arquivo final |
| 2026-09-24 | Desenvolvimento em **marcos com spec próprio** (ROADMAP/STATE) em vez de um spec único | evitar tarefa gigantesca |
| 2026-09-24 | Código e identificadores (inclusive nomes de etapas no config) em **inglês**; mensagens ao usuário em **PT-BR** | spec M0, D1 — pendente de revisão |
| 2026-09-24 | Dados em `~/.local/share/translaterany/` e config em `~/.config/translaterany/config.toml` (XDG) | spec M0, D2/D3 |
| 2026-09-24 | Runner por etapa e escopo `episode`/`series` já no M0; tipos de linha passam para o M1 | spec M0, D4/D5 |
| 2026-09-24 | Spec do M0 aprovado. Desvios registrados no plano: `LLMRequest`/`LLMResponse`/`Usage` como dataclasses; `inventory` sem `mtime`; módulos `reset`, `status`, `log`, `cli/app`; manifest corrompido → mensagem clara e código 1 | detectados ao validar o plano em protótipo |
| 2026-09-24 | M0 executado (modo direto): 101 testes, aceite nas duas séries de teste (14 e 65 episódios), interrupção real com SIGINT retomada corretamente | Ctrl+C durante a importação dos módulos (antes de o comando começar) ainda mostra traceback — avaliado na revisão final |
| 2026-09-24 | M1: abordagem A (parser próprio, cópia exata exceto texto); publicar só com tradução; remux substitui sem backup; PT-BR default, SDH removidas, demais sem default; base Full/Dialog > S&S, SDH nunca; `S01E01-02`; `series.toml` (faixa + estilos) | brainstorming do M1 |
| 2026-09-24 | Medições: Charlotte `Dialog` ⊇ `S&S` (não há faixas divididas nos casos de teste); ~7 mil eventos → ~515 textos únicos; extração EN idêntica após remux | base do spec M1 |
| 2026-09-24 | Spec M1 aprovado; desvios do plano incorporados ao spec: `cache_payload`, `enabled_by_default`, cenas no `classify`, `LC_ALL=C.UTF-8`, PT de terceiros em qualquer extensão, `run` em pasta de temporada, "Nenhuma série encontrada" | detectados ao prototipar o M1 |
| 2026-09-24 | M1 executado (modo direto): 228 testes; aceite real — 79 episódios, faixas conforme a tabela, `write.ass` idêntico em 79/79, Charlotte S01E01 com 377 unidades de diálogo, segunda execução em cache, pasta de temporada reconhecida, `temporada-teste/` intacta | |
| 2026-09-26 | Revisão final do M1 (Opus): 1 crítico (commit da Tarefa 1 sem o pacote `library` — corrigido) e 7 importantes corrigidos (separadores Unicode no parser, `--force` lembrado, permissões e backup no remux, `status`/`retry` em pasta de temporada, escolha manual preferindo faixa completa, publicação após renomear vídeo) + marca de tradução só quando o texto muda | |
| 2026-09-24 | Casos de teste reais em `temporada-teste/` (fora do git): *Charlotte* (simples) e *High School D×D* (difícil); testes automatizados só com dados sintéticos | mídia e legendas reais não entram no repositório |
| 2026-09-26 | M2 executado: 289 testes (+52 novos testes); camada LLM via `PydanticAIClient` (Ollama/OpenAI/Gemini), chunking semântico com overlap de contexto, preservação de marcadores inline (`⟦1⟧`), resiliência com fallback para texto original | |
| 2026-09-26 | M2 CLI e Pipeline: comandos `doctor` (checagens de Ollama/GPU/modelos) e `estimate` (contagem de tokens e estimativa de custos) implementados; `run` integrado com `PydanticAIClient` para Ollama; pipeline E2E validado | |
| 2026-09-26 | M3 executado: 364 testes (+75 novos testes); metadados canônicos via AniList/Jikan, etapas metadata, extract_terms e consolidate_memory integradas ao pipeline; persistência em YAML (characters, glossary, story) com precedência estrita (user > metadata > extracted); injeção de glossário por episódio e rastreamento de staleness com retry --stale; comando CLI memory e testes E2E | |
| 2026-09-27 | M4 executado: 396 testes (+22 novos testes); memória de tradução (TM) da série com precedência user > auto, fusão e redistribuição inteligente de frases partidas consecutivas, análise de contexto de cena por IA, tradução especializada de placas e músicas (com preservação estrita de karaokê/romaji), tradução contextualizada de diálogos com políticas de honoríficos ('keep') e palavrões ('faithful') e fallback neutro de gênero quando a confiança for baixa; pipeline consolidado com redistribute_sentences gerando UnitTexts final para write | |
| 2026-09-30 | M5 (brainstorming): checagens "núcleo leve" (sem spaCy, que vai para o M7) + fontTools; padrão Netflix PT-BR (CPS 17, CPL 42, 2 linhas; exceder = error); abordagem A — `MeteredLLM` no runner grava camada 1 no manifest (schema 2), etapa `quality_checks` no fim do pipeline grava camada 2 em `metrics.json`, `report` junta; saída terminal + `--json` + `--baseline`; linhas de base em `docs/baselines/` só com agregados | achado: uso de tokens não era persistido; bug `episode.id` no `redistribute_sentences` corrigido no M5 |
| 2026-09-30 | M5 executado (branch `m5-verificacoes-metricas`): `MeteredLLM` + manifest schema 2 (camada 1), etapa `quality_checks` + `metrics.json` (camada 2), comando `report` com `--json`/`--baseline`, correção de `episode.key` na TM; decisão: falhas de fontes viram achado `info` (`except Exception`), nunca derrubam o episódio; revisão final: linhas compostas não sofrem CPL/linhas, taxa por checagem = linhas afetadas (não achados), `ChecksConfig` com validação de faixas | 482 testes; aceite real pendente |
| 2026-09-30 | **Primeiro uso real** (Charlotte S01E01, modelos locais): (1) camada Ollama migrada para a API nativa `/api/chat` — o `/v1` ignorava `num_ctx` (tudo em 4096, prompts truncados em silêncio), não desligava o raciocínio do gemma4 e exigia *tools*, que o TranslateGemma não tem; `think` por modelo (desligado), gemma4 `num_ctx` 16384, translategemma 8192. (2) Tradução passa a ser **uma fala por chamada** (`max_lines_per_batch=1`): em lotes o TranslateGemma desalinhava IDs e deslocava traduções. (3) `scene_analysis` **por cena** (blocos de até 40 falas) — antes mandava o episódio inteiro e estourava o contexto | run final: 24,8 min/episódio (cena 11 min, diálogo 11 min); alinhamento corrigido; 346 falas, 95 com falante de alta confiança |
| 2026-09-30 | Músicas **puladas por padrão** (`[stages.translate_songs.options] translate = true` para traduzir); legibilidade: diálogo vai ao modelo sem `\N` e com orçamento de caracteres (max_cps × duração), quebra de linha refeita pelo CPL | Charlotte S01E01: linhas com problema de leitura 34,3% → **8,7%** (original EN: 12%), CPS p95 24 → 19; 0 de 30 unidades de música traduzidas; ~11 min de tradução com a análise de cena em cache |
| 2026-09-30 | **M6 — Refinamento I:** etapas `review_meaning` (todas as falas, blocos por cena, só fidelidade) e `colloquial` (só falas triadas) no papel `review` (Gemma4), antes da redistribuição, sobre frases inteiras; resposta só com edições validadas (`apply_edits`: id, vazio, inalterado, marcadores/tags, reversão, piora pelas checagens de sentido; texto aceito normalizado); triagem por regras; nova checagem `profanity_added`; `redistribute_sentences` lê a última etapa com `produces_dialogue` | 553 testes; aceite real pendente |
| 2026-10-01 | **Aceite real do M6** (Charlotte S01E01, tradução em cache = mesma entrada do M5): `review_meaning` 80 s (16 edições aplicadas, 2 recusadas) e `colloquial` 44 s (23 falas triadas, 17 aplicadas, 6 recusadas) — **+2 min/episódio**. Corrigiu 4 palavrões inventados, "cúmplice"→"culpado", fala truncada, fala em inglês e concordâncias. Auditoria de 60 falas sorteadas (semente 42): M5 ≈ 80% corretas / 5% erro grave → M6 **85% corretas / 11,7% deslizes / 3,3% erro grave** | amostra pequena (IC amplo); restam erros de sentido não detectados ("Que barulho é esse?", "Me ajudar a quê?") |
| 2026-10-01 | **Baseline M6 (Charlotte S01E01–04) e correções:** (1) checagem `prompt_leak` adicionada para barrar instruções do prompt (`máx. N`, `[u...]`) e emojis espúrios; (2) `merge_dialogue_units` passa a adotar a menor duração individual (`shortest_ms`) nas falas repetidas para não inflar o orçamento de caracteres; baseline salva em `docs/baselines/2026-10-01-m6-charlotte-s01e01-04.json` | 558 testes passando |
| 2026-10-01 | **M7 — Refinamento II:** 4 etapas sequenciais (`treatment_consistency`, `adapt`, `orthography`, `final_readthrough`) entre `colloquial` e `redistribute_sentences`; cliente LanguageTool HTTP com degradação graciosa e isenções (nomes de personagens e termos do glossário); triagem pronominal/gênero por pares de alta confiança; condensação de CPS > 17 com orçamento de caracteres; leitura corrida final em PT-BR por cena; checagem `doctor` do LanguageTool; revisão final tratou isenções e integridade de marcadores | 583 testes passando |
| 2026-10-01 | **M8 — Portões e laço do QA (Fim da v1):** StageGate com escada de escalonamento local (feedback + redução unitária) e detecção de oscilação; checagens finais exclusivas (sintaxe ASS, integridade de eventos, timing); algoritmo de blame retroativo no histórico de artefatos; etapa QALoopStage com reprocessamento em cascata pontual e integração determinística com orthography; artefato qa_report.json e aviso de modelo no report; WriteStage respeita text_source explícito; gate.reset() previne vazamento de estado | 650 testes passando; conclusão da v1 |
| 2026-10-02 | **Lançamento v1.0.0 & Definição da v1.1:** v1.0.0 concluída e validada em produção nos eps 1-4 de High School DxD (659 testes passando); definida a v1.1 com OCR de legendas em imagem (PGS/VobSub) e suporte universal a qualquer idioma de entrada/saída (`source_language` e `target_language`) | expansão para mídias físicas e pares multilíngues arbitrários |
| 2026-10-04 | **M9 — Suporte Universal a Idiomas (v1.1):** Catálogo universal `LanguageRegistry` com resolução por código canônico ou aliases flexíveis; interface `LanguageProfile` com implementações completas `PortugueseProfile` (100% de paridade), `SpanishProfile`, `EnglishProfile` e fallback resiliente `GenericProfile`; injeção dinâmica de `source_language` e `target_language` em todos os prompts de IA (`translate_dialogue`, `translate_signs`, `translate_songs`, `review_meaning`, `final_readthrough`); triagem gramatical e de tratamento orientadas pelo perfil do idioma alvo; LanguageTool parametrizado por código de idioma; remux e publicação com nomenclatura `.{code}.ass` e flags `0:{code}` e nome legível de faixa | 686 testes passando (+26 novos testes multilíngues); zero regressões |
| 2026-10-05 | **M10 — OCR de Legendas Gráficas (v1.1):** Suporte nativo a legendas em imagem PGS (`.sup`) e VobSub DVD (`.sub`/`.idx`) via pure-Python + Pillow (zero OpenCV/PyTorch); seletor de faixas prioriza diálogo completo gráfico sobre placas/músicas em texto; extração via `mkvextract`; motor de OCR paralelo via Tesseract com hOCR para preservação de itálicos (`{\i1}...{\i0}`), deduplicação SHA-256 de frames e `ThreadPoolExecutor`; nova etapa `OCRStage` no pipeline gerando `.ocr.ass` com estilos de posicionamento vertical (`Top`/`\an8`, `Sign`/`\an5`, `Default`) e bypass transparente para faixas de texto; binding dinâmico de `NormalizeStage` e `WriteStage` ao `ocr`; checagem `doctor` para Tesseract e pacotes de idioma do `source_language` | 713 testes passando (+27 novos testes de OCR e E2E); zero regressões; v1.1 concluída |

---

## Pendências e perguntas em aberto

| Pergunta | Quando decidir |
|---|---|
| Revisão de sentido deixa passar erros sem sinal (sentido trocado, pessoa errada, título do episódio alucinado em fala) | M7/M8 (leitura corrida, QA) |
| Uso real: o orçamento de caracteres às vezes faz o modelo trocar sentido ("What's this I hear?" → "Que barulho é esse?") ou **inventar palavrão** ("colar em tudo, seu merda.") — reforçar no prompt: não acrescentar ofensas nem mudar o sentido ao condensar | M6 (revisão de sentido) |
| Uso real: 17 placas com muitas tags por letra ficam em inglês (marcadores perdidos → fallback) | avaliar |
| Desempenho: 24,8 min/episódio; `scene_analysis` gera ~22 mil tokens de saída (6 campos por fala) — enxugar campos | M6 |
| Teste do M2 grava pastas `test-m2-pipeline-*` no diretório de dados real | corrigir |
| M5: `font_glyphs` só aparece no `report --episode`; falta um resumo por série | quando incomodar (M6+) |
| M5: episódio pulado (`SkipEpisode`) aparece como "sem métricas (rode run)"; `--episode` inexistente diz "nenhuma métrica" em vez de "episódio não encontrado" | quando incomodar (M6+) |
| M5: entradas antigas da TM (gravadas antes da correção `episode.key`) seguem sem episódio até o episódio ser reprocessado | inofensivo; opcional |
| Quais modelos locais concretos usar por etapa (famílias 7B–14B Q4 que cabem em 12 GB) | spec do M2 |
| Obter chave de API Gemini e/ou OpenAI (opcional) | antes de testar perfis `hibrido`/`nuvem` (M2) |
| Política global padrão de honoríficos (manter / adaptar / remover) | decidida no M4 (`honorifics = "keep"`) |
| Nível padrão de palavrão | decidida no M4 (`profanity = "faithful"`) |
| **Casamento pasta/temporada → AniList** quando o `.nfo` só tem TVDB/TMDB: busca por título + ano + nº de eps, ou usar bases comunitárias de mapeamento (ex.: projetos Anime-Lists / Fribb, que ligam TVDB/TMDB ↔ AniDB/AniList/MAL) — avaliar | spec do M3 |
| **Escopo da memória da série**: por pasta (show inteiro, todas as temporadas — glossário unificado) ou por temporada/entrada AniList? Metadados vêm por entrada AniList e precisam ser combinados | spec do M3 |
| Modelos locais que **recusam conteúdo** (fan service) — critério na escolha dos modelos | spec do M2 |
| LanguageTool via Docker ou `.jar` | spec do M7 |

---

## Casos de teste reais (cobaias)

Local: `temporada-teste/` (ignorada pelo git — **nunca versionar mídia nem trechos das legendas reais**; testes automatizados usam só dados sintéticos, os casos reais são para testes manuais/de fumaça).

### Caso 1 — *Charlotte (2015)*: o caso simples

| Característica | Valor | Implicação |
|---|---|---|
| Conteúdo | 13 eps (`Season 1/`) + 1 especial (`Specials/S00E02`), todos Bluray | uma temporada = uma entrada no AniList |
| Estrutura | padrão Jellyfin/Sonarr, `tvshow.nfo`, `season.nfo`, `.nfo` por episódio | sinopses locais disponíveis além da Jikan |
| Sobras de upgrade | `.nfo`/thumbs órfãos de versões HDTV antigas ao lado dos Bluray | varredura parte dos `.mkv`, ignora metadados órfãos |
| Faixas de legenda | **`Dialog - ENG` + `S&S`** — medido: `Dialog` já contém a `S&S` | basta a `Dialog` |
| Anexos | ~17 fontes por episódio | checagem de acentos e preservação no remux |
| Áudio | inglês + japonês | — |

### Caso 2 — *High School D×D (2012)*: o caso difícil

| Característica | Valor | Implicação |
|---|---|---|
| Conteúdo | **4 temporadas** (12 eps cada, HDTV) + **17 especiais** (S00E02–S00E18, maioria Bluray) numa única pasta de série | uma pasta (TVDB) ↔ **várias entradas no AniList** (uma por temporada + OVAs/especiais) |
| IDs no `tvshow.nfo` | TVDB, TMDB, IMDb — **sem AniList/MAL** | casamento temporada → AniList não sai direto do `.nfo` |
| Faixas (T1–T4) | **`Full Subtitle` + `Signs & Songs`** | aqui o `Full` já contém tudo; o `S&S` serve a quem assiste dublado — **semântica oposta ao Caso 1** |
| Faixas (T4) | Full de um grupo (`Tensai/IK`) e S&S de **outro grupo** (`LostYears`) | estilos/convenções diferentes entre faixas do mesmo episódio |
| Faixas (especiais) | alguns com **duas faixas `Full` de grupos diferentes** (`CBM/IK` e `ADZ/IK`); outros com uma só | regra de desempate entre faixas "Full" equivalentes |
| Fansubs por temporada | FFF/SCY → FFF → Tensai/IK | estilo de tradução EN muda entre temporadas; glossário precisa unificar |
| Anexos | de 3 a 28 fontes por episódio | — |
| Áudio | eng + jpn nas temporadas; **só jpn** nos especiais | — |
| Nomes de arquivo | Unicode no caminho (`×`, `☆`, `~`) | slugs e caminhos precisam lidar com Unicode |
| Conteúdo | fan service intenso | **teste real de recusa por filtro de segurança** (nuvem) e de modelos locais que recusam conteúdo |

## Pré-requisitos de ambiente

| Item | Situação |
|---|---|
| Python 3.14 via `uv` | ✅ |
| `ffmpeg` / `ffprobe` | ✅ instalado |
| `mkvtoolnix` (`mkvextract`, `mkvmerge`) | ✅ v102.0 via Homebrew (`/home/linuxbrew/.linuxbrew/bin`) |
| Ollama | ✅ instalado / Docker |
| LanguageTool | ❌ instalar antes do M7 |
| GPU | NVIDIA RTX 3060 12 GB · 46 GB RAM · 12 threads |

---

## Próximos passos

1. **Aceite real do M5:** rodar Charlotte com modelos locais, gerar `translaterany report ... --json docs/baselines/<data>-m5-charlotte.json` e registrar os números principais aqui.
2. Validação prática do pipeline do M4 em casos de teste reais com modelos locais.


