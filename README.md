# TranslaterAny 🚀

Tradução automática de legendas de anime (**EN → PT-BR**) com IA **local-first**, executada em um pipeline multiestágio determinístico com foco em alta qualidade, naturalidade coloquial e conformidade técnica de legendagem.

---

## 🌟 Destaques

- **Local-First & Privado**: Funciona 100% offline via [Ollama](https://ollama.ai) e [LanguageTool](https://languagetool.org) local.
- **Pipeline em 24 Estágios**: Cada etapa resolve uma responsabilidade única (análise de cena, tradução, adaptação, coerência pronominal/gênero, orçamento de caracteres, ortografia e QA).
- **Resolução de Gênero e Tratamento**: Integração com metadados do AniList e memória contínua da série para garantir concordância perfeita de artigos (*a presidente / o servo*) e pronomes (*você / tu / senhor*).
- **Controle Rígido de Legibilidade**: Condensação inteligente de falas para respeitar limites de CPS (caracteres por segundo) e CPL (caracteres por linha), com quebra sintática de linhas (`\N`).
- **Blindagem Ortográfica Determinística**: LanguageTool local com isenção automática de nomes próprios japoneses e termos do glossário.
- **Portões de Qualidade (StageGate) & QA Loop**: Reversão automática de edições que introduzam regressões e laço de auto-reparo para falhas de tradução ou ritmo.

---

## 📋 Pré-requisitos

1. **Python 3.14+** (gerenciado via [`uv`](https://github.com/astral-sh/uv))
2. **MKVToolNix** (`mkvmerge`, `mkvextract`) instalados no sistema
3. **Ollama** com os modelos recomendados:
   - `translategemma:12b` (modelo de tradução)
   - `gemma4:12b` (modelo para análise, refinamento e QA)
4. **Docker** (para o serviço local do LanguageTool)

---

## 🐳 LanguageTool (Docker Compose)

O projeto inclui um `docker-compose.yml` otimizado utilizando imagem leve do LanguageTool (`meyay/languagetool:latest`, ~300 MB) na porta `8010`:

```bash
# Iniciar o LanguageTool em segundo plano
docker compose up -d

# Visualizar logs
docker compose logs -f

# Parar o serviço
docker compose down
```

---

## 🔍 Diagnóstico do Ambiente

Valide se todas as ferramentas, portas, conectividade e modelos locais estão prontos:

```bash
uv run translaterany doctor
```

O comando verifica:
- Instalação de `mkvmerge` e `mkvextract`
- Conectividade com a API do Ollama e presença dos modelos necessários
- Disponibilidade do serviço LanguageTool em `http://localhost:8010`
- Conectividade com metadados externos (AniList/Jikan)

---

## ⚡ Comandos Principais (CLI)

### 1. Processar uma Série ou Temporada
Executa o pipeline completo em todos os episódios da pasta da série:

```bash
uv run translaterany run "/caminho/para/Nome da Serie (Ano)"
```

### 2. Estimar Tokens e Custo
Gera uma estimativa de volume de falas, chamadas LLM e tempo de processamento antes de rodar:

```bash
uv run translaterany estimate "/caminho/para/Nome da Serie (Ano)"
```

### 3. Reexecutar / Reprocessar (Retry)
Permite reabrir episódios específicos a partir de uma etapa desejada:

```bash
# Reprocessar um episódio específico a partir de uma etapa
uv run translaterany retry "/caminho/para/Serie" --episode S01E03 --from treatment_consistency

# Reprocessar apenas episódios com falhas
uv run translaterany retry "/caminho/para/Serie" --failed
```

### 4. Consultar Status e Progresso
Exibe o estado de cada episódio no pipeline:

```bash
uv run translaterany status "/caminho/para/Nome da Serie (Ano)"
```

### 5. Relatórios de Qualidade
Visualiza métricas agregadas de leitura (CPS/CPL), taxa de edição e diagnósticos de QA:

```bash
uv run translaterany report "/caminho/para/Nome da Serie (Ano)"
```

### 6. Gerenciamento de Memória da Série
Consulta e gerencia o glossário e os personagens persistidos na série:

```bash
uv run translaterany memory show "/caminho/para/Nome da Serie (Ano)"
uv run translaterany memory sync "/caminho/para/Nome da Serie (Ano)"
```

---

## 🛠️ Arquitetura do Pipeline

```text
[Vídeo MKV]
   │
   ├─► inventory & metadata (AniList / Jikan)
   ├─► extract & normalize (Extração ASS / normalização)
   ├─► classify & scene_analysis (Diálogo, placas, músicas e falantes da cena)
   ├─► extract_terms & consolidate_memory (Glossário e Personagens)
   ├─► translate_dialogue / signs / songs (Tradução contextualizada)
   │
   ▼ [Refinamento & Polimento]
   ├─► review_meaning (Verificação semântica)
   ├─► colloquial (Adaptação de estilo e naturalidade PT-BR)
   ├─► treatment_consistency (Unificação de pronomes você/tu e artigos de gênero)
   ├─► adapt (Condensação para limites estritos de CPS)
   ├─► orthography (LanguageTool local com isenções de nomes próprios)
   ├─► final_readthrough (Leitura contínua da cena em português)
   │
   ▼ [Controle de Qualidade & Entrega]
   ├─► redistribute_sentences (Ajuste e quebras de linha com \N)
   ├─► qa_loop (Auditoria e auto-reparo guiado)
   ├─► write & publish (Gravação final em .pt-BR.ass)
```

---

## 🧪 Testes Automatizados

O projeto conta com ampla cobertura de testes de unidade e integração:

```bash
# Executar toda a suíte de testes
uv run pytest
```

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte `LICENSE` para mais informações.
