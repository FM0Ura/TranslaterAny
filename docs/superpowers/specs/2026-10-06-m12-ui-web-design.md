# Spec — Marco M12: UI Web e API RESTful Desacoplada (v1.3)

> **Status:** Aprovado em brainstorming  
> **Data:** 2026-10-06  
> **Versão do TranslaterAny:** v1.3.0  
> **Branch de trabalho sugerido:** `m12-ui-web`

---

## 1. Visão Geral e Objetivos

O TranslaterAny opera hoje como uma ferramenta CLI de alta precisão. O Marco M12 introduz uma **Interface Web (UI Web)** e uma **API RESTful completa**, permitindo:

1. **Gestão Visual da Biblioteca:** Navegar pelas séries com capas (posters/banners), visualizar o status de tradução de cada episódio e inspecionar detalhes do MKV.
2. **Execução e Controle em Tempo Real:** Disparar execuções de episódios ou temporadas inteiras em segundo plano, com barra de progresso etapa por etapa e console de logs em tempo real via **Server-Sent Events (SSE)**.
3. **Controle de Ciclo de Vida (Pausar / Retomar / Cancelar):** Capacidade de pausar a execução em fronteiras seguras de etapas sem corromper artefatos e retomar de onde parou.
4. **Editor Interativo de Memória da Série:** Interface visual para gerenciar as fichas de personagens (`characters.yaml`), termos do glossário (`glossary.yaml`) e enredo (`story.yaml`) sem edição manual de arquivos no disco.
5. **Grafo / Pipeline Visual Plugável:** Representação visual interativa (DAG) de todas as 28 etapas do pipeline, permitindo ligar e desligar etapas tanto em nível global (`config.toml`) quanto específico por série (`series.toml`).
6. **Central de Configurações e Diagnóstico:** Ajustar modelos de IA, parâmetros do Ollama/LanguageTool, limites de legibilidade (CPS/CPL) e inspecionar diagnósticos do sistema (`doctor`) diretamente pelo navegador.
7. **Desacoplamento Arquitetural Estrito:** Backend construído com API RESTful JSON de primeira classe (`/api/v1`), garantindo que a camada de visualização em SSR/HTMX possa ser facilmente substituída ou complementada no futuro por clientes dedicados (React, Vue, Tauri desktop, etc.).

---

## 2. Arquitetura em Três Camadas

Para garantir isolamento, manutenibilidade e facilidade de migração futura, o módulo web adota separação estrita de responsabilidades:

```
┌────────────────────────────────────────────────────────┐
│                   Camada Visual (UI)                   │
│   [Templates Jinja2 + HTMX 2.x + Tailwind CSS local]   │
└─────────────────────────────┼──────────────────────────┘
                              │ Consome via HTTP / SSE
                              ▼
┌────────────────────────────────────────────────────────┐
│               API RESTful JSON (/api/v1/)              │
│   Rotas FastAPI padronizadas com modelos Pydantic       │
└─────────────────────────────┼──────────────────────────┘
                              │ Invoca serviços desacoplados
                              ▼
┌────────────────────────────────────────────────────────┐
│              Camada de Serviços (Service Layer)        │
│   SeriesService  │  JobService  │  PipelineService     │
│             ConfigService       │  MemoryService       │
└─────────────────────────────┼──────────────────────────┘
                              │ Executa pipelines e persiste
                              ▼
┌────────────────────────────────────────────────────────┐
│               Core do TranslaterAny                    │
│   PipelineRunner │ ArtifactStore │ StageRegistry       │
└────────────────────────────────────────────────────────┘
```

---

## 3. Estrutura de Módulos (`src/translaterany/web/`)

```
src/translaterany/web/
├── __init__.py
├── app.py                  # Instância FastAPI, middlewares (CORS, Auth), montagem de static/templates
├── jobs.py                 # Fila assíncrona de jobs, JobRecord, JobStatus e SSE broadcaster
├── services/
│   ├── __init__.py
│   ├── series_service.py   # Descoberta de séries, inventário de episódios e artefatos
│   ├── memory_service.py   # Leitura e escrita de characters.yaml, glossary.yaml e story.yaml
│   ├── pipeline_service.py # Inspeção e alteração do grafo de etapas (global e por série)
│   ├── config_service.py   # Leitura e gravação do config.toml com validação Pydantic
│   └── job_service.py      # Agendamento, pausa, retomada e cancelamento de execuções
├── api/
│   ├── __init__.py
│   ├── series.py           # Endpoints /api/v1/series/...
│   ├── memory.py           # Endpoints /api/v1/series/{key}/memory/...
│   ├── pipeline.py         # Endpoints /api/v1/pipeline/...
│   ├── config.py           # Endpoints /api/v1/config/...
│   ├── doctor.py           # Endpoints /api/v1/doctor/...
│   └── jobs.py             # Endpoints /api/v1/jobs/... (incluindo stream SSE)
├── pages/
│   ├── __init__.py
│   ├── dashboard.py        # Rotas HTML para renderizar páginas via Jinja2 + HTMX
│   ├── series.py
│   ├── memory.py
│   ├── pipeline.py
│   └── settings.py
├── templates/              # Templates Jinja2
│   ├── base.html           # Layout comum (Dark Mode, Navbar, Drawer de Jobs)
│   ├── components/         # Fragmentos parciais HTMX (cards, nós de grafo, tabelas)
│   ├── dashboard.html      # Grid de séries
│   ├── series.html         # Detalhes da série e tabela de episódios
│   ├── memory.html         # Editor de personagens, glossário e sinopse
│   ├── pipeline.html       # Construtor visual de grafo de etapas
│   ├── inspector.html      # Comparador de legendas e relatório de QA
│   └── settings.html       # Painel de configurações
└── static/                 # Assets 100% locais (autonomia offline)
    ├── css/
    │   └── tailwind.min.css # CSS compilado do Tailwind
    ├── js/
    │   ├── htmx.min.js      # Biblioteca HTMX 2.x
    │   └── sse.js           # Extensão oficial SSE para HTMX
    └── img/
        └── placeholder.png  # Capa padrão para animes sem poster
```

---

## 4. Gerenciador de Jobs em Background & Ciclo de Vida

### 4.1. Estados do Job (`JobStatus`)

```python
class JobStatus(StrEnum):
    PENDING = "pending"        # Na fila aguardando início
    RUNNING = "running"        # Executando no worker
    PAUSED = "paused"          # Pausado entre etapas/episódios
    COMPLETED = "completed"    # Concluído com sucesso
    FAILED = "failed"          # Interrompido por erro
    CANCELLED = "cancelled"    # Abortado pelo usuário
```

### 4.2. Registro do Job (`JobRecord`)

```python
class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    series_key: str
    series_name: str
    episode_key: str | None = None          # None = temporada completa
    stage_from: str | None = None            # Etapa de início em caso de retry
    status: JobStatus = JobStatus.PENDING
    current_stage: str = ""
    current_unit: str = ""
    progress_percent: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
```

### 4.3. Mecânica de Pausa, Retomada e Cancelamento

1. O `JobManager` executa cada job em uma thread dedicada (`ThreadPoolExecutor(max_workers=1)`), mantendo apenas um processamento pesado por vez para não sobrecarregar a GPU local.
2. Cada job recebe um token de controle com flags de pausa (`pause_event = threading.Event()`) e cancelamento (`cancel_event = threading.Event()`).
3. Entre a conclusão de cada etapa e entre episódios, o runner consulta o token:
   - Se `cancel_event.is_set()`: o job finaliza imediatamente como `CANCELLED`.
   - Se `not pause_event.is_set()`: o runner suspende a execução, altera o estado para `PAUSED` e emite evento SSE de pausa.
   - Quando o endpoint `/api/v1/jobs/{id}/resume` é acionado: `pause_event.set()` é chamado, reativando o runner no mesmo ponto.

---

## 5. Especificação da API RESTful JSON (`/api/v1/`)

Todas as rotas de API retornam e aceitam JSON puro:

### 5.1. Séries e Episódios
- `GET /api/v1/series`: Lista todas as séries da biblioteca com metadados básicos e contagem de episódios concluídos.
- `GET /api/v1/series/{key}`: Detalhes completos da série, incluindo poster, backdrop, sinopse e lista de episódios.
- `GET /api/v1/series/{key}/episodes/{ep}`: Dados detalhados do episódio (faixas de áudio/legenda detectadas, histórico de manifest e status).
- `GET /api/v1/series/{key}/episodes/{ep}/subtitles`: Retorna a legenda `.pt-BR.ass` gerada ou eventos alinhados para comparação.
- `GET /api/v1/series/{key}/episodes/{ep}/qa_report`: Dados estruturados do relatório de QA e violações de CPS/CPL.

### 5.2. Memória da Série
- `GET /api/v1/series/{key}/memory`: Retorna personagens (`characters.yaml`), termos de glossário (`glossary.yaml`) e enredo (`story.yaml`).
- `POST /api/v1/series/{key}/memory/characters`: Adiciona ou atualiza um personagem.
- `DELETE /api/v1/series/{key}/memory/characters/{name}`: Remove um personagem.
- `POST /api/v1/series/{key}/memory/glossary`: Adiciona ou atualiza um termo do glossário.
- `DELETE /api/v1/series/{key}/memory/glossary/{term}`: Remove um termo.
- `PUT /api/v1/series/{key}/memory/story`: Atualiza a sinopse e anotações narrativas.

### 5.3. Grafo de Pipeline Plugável
- `GET /api/v1/pipeline`: Retorna o grafo de etapas do pipeline global com status de ativação (`enabled`), dependências (`inputs`) e escopo (`scope`).
- `PUT /api/v1/pipeline/toggle`: Ativa ou desativa uma etapa no pipeline global (`config.toml`).
- `GET /api/v1/series/{key}/pipeline`: Retorna o grafo da série, indicando se usa a configuração global ou personalizada (`series.toml`).
- `PUT /api/v1/series/{key}/pipeline`: Define a lista de etapas ativas e configurações específicas da série.

### 5.4. Jobs e Controle
- `GET /api/v1/jobs`: Lista todos os jobs recentes (ativos e finalizados).
- `POST /api/v1/jobs/run`: Enfileira novo job para série ou episódio. Parâmetros: `series_key`, `episode_key` (opcional), `from_stage` (opcional), `force` (bool).
- `POST /api/v1/jobs/{id}/pause`: Pausa o job em execução.
- `POST /api/v1/jobs/{id}/resume`: Retoma um job pausado.
- `POST /api/v1/jobs/{id}/cancel`: Cancela o job.
- `GET /api/v1/jobs/{id}/stream`: Stream SSE contendo eventos `progress`, `log`, `status`, `error`.

### 5.5. Configurações e Diagnóstico
- `GET /api/v1/config`: Lê a configuração ativa consolidada do `config.toml`.
- `PUT /api/v1/config`: Atualiza e salva o `config.toml` com validação estrita via `AppConfig`.
- `GET /api/v1/doctor`: Executa os diagnósticos de ambiente em tempo real (GPU, Ollama, Tesseract, LanguageTool, ffmpeg).

---

## 6. Telas da Interface Web (Jinja2 + HTMX)

1. **Dashboard da Biblioteca (`/`):**
   - Grid moderno com posters, barra de progresso visual (ex.: "12/12 episódios prontos") e filtros rápidos por status.
2. **Visão da Série (`/series/{key}`):**
   - Banner panorâmico superior, sinopse, metadados AniList e abas: *Episódios*, *Memória*, *Pipeline da Série*, *Relatório de Qualidade*.
3. **Grafo Interativo de Pipeline (`/pipeline` e `/series/{key}/pipeline`):**
   - Fluxograma interativo conectando os nós das etapas.
   - Nós com ícones temáticos e switch ON/OFF.
   - Modo "Bypass" com nós pontilhados para etapas desativadas.
   - Gaveta lateral de opções para customizar modelo e parâmetros ao clicar em um nó.
4. **Editor de Memória da Série (`/series/{key}/memory`):**
   - Sub-abas: *Personagens*, *Glossário*, *História*.
   - Formulários rápidos em modais para cadastro e edição instantânea.
5. **Inspetor de Episódio & Comparador Lado a Lado (`/series/{key}/episodes/{ep}`):**
   - Tabela comparativa da fala original (EN/JA) contra a tradução final (PT-BR) com badge do falante e CPS.
   - Botão para download direto do arquivo `.pt-BR.ass`.
6. **Central de Configurações (`/settings`):**
   - Formulários organizados em abas: *Idiomas e Políticas*, *Modelos de IA*, *Diarização de Áudio (M11)*, *Legibilidade e QA*, *Caminhos e Servidor*.
7. **Drawer Global de Execução ao Vivo:**
   - Botões *⏸️ Pausar*, *▶️ Retomar*, *⏹️ Cancelar*.
   - Linha do tempo visual das 28 etapas acendendo em verde.
   - Terminal integrado com auto-scroll consumindo o stream SSE.

---

## 7. Comando CLI e Empacotamento

### 7.1. Comando Typer (`translaterany web`)
```bash
translaterany web [OPTIONS]
```
- `--host, -h <str>`: Padrão `127.0.0.1` (suporta `0.0.0.0`).
- `--port, -p <int>`: Padrão `8080`.
- `--open-browser / --no-open`: Abre o navegador padrão automaticamente.
- `--reload`: Modo de desenvolvimento com recarga automática de templates/código.

### 7.2. Dependências (`pyproject.toml`)
- `fastapi>=0.115.0`
- `uvicorn>=0.32.0`
- `jinja2>=3.1.4`
- `python-multipart>=0.0.12`

Assets estáticos (Tailwind minificado, HTMX 2.x, extensão SSE) são incluídos no diretório `src/translaterany/web/static/` para garantia de funcionamento 100% offline.

---

## 8. Estratégia de Testes

1. **Testes Unitários da Camada de Serviços (`tests/web/services/`):**
   - `test_series_service.py`: listagem e metadados de séries a partir de dados reais ou mock de `ArtifactStore`.
   - `test_memory_service.py`: adição, edição e remoção de personagens e glossário com validação de idempotência.
   - `test_pipeline_service.py`: alteração e persistência de etapas ativas/desativadas.
2. **Testes do Gerenciador de Jobs (`tests/web/test_job_manager.py`):**
   - Validação da fila assíncrona, execução de job sintético, captura de logs e transições de estado (`PENDING` $\rightarrow$ `RUNNING` $\rightarrow$ `PAUSED` $\rightarrow$ `COMPLETED`).
3. **Testes da API RESTful (`tests/web/api/`):**
   - Testes com `fastapi.testclient.TestClient`:
     - Verificação de respostas HTTP 200 e schemas JSON das rotas `/api/v1/...`.
     - Teste do endpoint SSE com recepção de chunks `text/event-stream`.
4. **Testes de Integração do Comando CLI (`tests/web/test_cli_web.py`):**
   - Inicialização do comando `translaterany web` com flags customizadas.
5. **Regressão Zero:**
   - Manutenção de todos os 746 testes existentes passando com 100% de sucesso.

---

## 9. Critérios de Conclusão (Definition of Done)

- [ ] Servidor FastAPI implementado com rotas desacopladas em `/api/v1/` e páginas SSR/HTMX.
- [ ] Gerenciador de jobs em background com suporte a `PAUSED`, `RESUME`, `CANCEL` e streaming SSE.
- [ ] Grafo de pipeline interativo funcional (visualização e toggles de etapas globais e por série).
- [ ] Editor visual de memórias (`characters.yaml`, `glossary.yaml`, `story.yaml`) integrado.
- [ ] Comparador de legendas lado a lado funcional para episódios processados.
- [ ] Painel de configurações com teste de conexão com Ollama e LanguageTool.
- [ ] Comando CLI `translaterany web` operacional.
- [ ] Todos os novos testes da Web UI passando e suíte completa sem regressões.
