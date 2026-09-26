# M3 — Memória da série · Design

- **Marco:** M3 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-26
- **Status:** proposto (2026-09-26) · plano: pendente
- **Depende de:** M0 ([spec](2026-09-24-m0-fundacao-design.md)), M1 ([spec](2026-09-24-m1-midia-legendas-design.md)) e M2 ([spec](2026-09-26-m2-camada-ia-traducao-design.md))

---

## 1. Objetivo

Implementar a **Fase 1 do Pipeline (Análise da Série)** e o subsistema de **Memória da Série** (`translaterany.memory`), garantindo consistência semântica, terminológica e de tom ao longo de todos os episódios de uma série.

Ao fim do M3:
1. O sistema obtém metadados canônicos de animes via **AniList** (GraphQL) e **Jikan / MyAnimeList** (sinopses por episódio via REST), com cache persistente em disco e respeito estrito a limites de requisição;
2. Executa a análise da série em três etapas integradas ao `DEFAULT_PIPELINE`:
   - **`MetadataStage` (escopo `series`):** busca e estrutura dados canônicos externos (AniList/Jikan);
   - **`ExtractTermsStage` (escopo `episode`, com IA):** varre as falas normalizadas de cada episódio e a sinopse correspondente, extraindo termos candidatos, entidades, lugares, golpes e estilos de fala;
   - **`ConsolidateMemoryStage` (escopo `series`, com IA):** consolida as extrações dos episódios em um glossário coerente e fichas de personagens, gravando artefato `consolidate_memory.json`;
3. Persiste a memória em arquivos YAML editáveis pelo usuário (`glossary.yaml`, `characters.yaml`, `story.yaml`) com precedência estrita (`user` > `metadata` > `extracted`);
4. A etapa `StageTranslateDialogue` (M2) passa a receber o **glossário filtrado para o episódio** e as **fichas de personagens**, gravando no seu artefato (`translate_dialogue.json`) os termos utilizados e seus respectivos hashes (`used_terms: dict[str, str]`);
5. Suporta rastreamento de staleness: editar um termo em `glossary.yaml` marca os episódios afetados como desatualizados no comando `status` para reprocessamento seletivo com `translaterany retry --stale`.

---

## 2. Fora do escopo

| Item | Onde |
|---|---|
| Tradução de placas (`sign`), canções (`song`), e telas | M4 |
| Atribuição de falantes por cena e contexto situacional visual | M4 |
| União e redistribuição de frases partidas entre eventos | M4 |
| Métricas de CPS (caracteres por segundo), comprimento de linhas e comando `report` | M5 |
| Revisão de sentido e ajuste de coloquialidade em etapas dedicadas | M6 |
| Coerência de pronomes/tratamento (tu vs você) e LanguageTool | M7 |
| Portões de qualidade e laço fechado de QA com blame | M8 |

---

## 3. Evidências do ambiente e APIs externas

| Item | Característica | Implicação |
|---|---|---|
| **AniList API** | GraphQL pública (`https://graphql.anilist.co`), rate limit de 90 req/min, sem chave de API obrigatória para leitura. | Consultas para identificação de séries e personagens (nomes romanizados, nativos em kanji, gênero, papel `MAIN`/`SUPPORTING`). Cache em disco obrigatório em `<data_dir>/cache/anilist/`. |
| **Jikan API (MAL)** | REST pública (`https://api.jikan.moe/v4`), rate limit de 3 req/s (60 req/min). | Fornece sinopses por episódio (`/v4/anime/{idMal}/episodes` ou detalhes individuais) a partir do `idMal` retornado pelo AniList. Rate-limiter com backoff e cache em disco obrigatórios em `<data_dir>/cache/jikan/`. |
| **Modelo de IA para Extração** | `gemma4:12b` (local via Ollama) configurado no perfil `local` em `llm.profiles.local.review`. | Tarefa de extração de termos e consolidação é analítica; utiliza o modelo de revisão/raciocínio configurado. |
| **Isolamento de Testes** | Sandbox bloqueia requisições externas para `graphql.anilist.co` e `api.jikan.moe`. | Testes automatizados da suíte (`pytest`) devem ser 100% sintéticos e usar mocks HTTP (`monkeypatch` ou `httpx` custom transport com payloads JSON reais de amostra). |

---

## 4. Decisões acordadas

| # | Decisão | Origem |
|---|---|---|
| **D1** | **Casamento Híbrido Série ↔ AniList:** Busca automatizada no AniList por título e ano (lidos do `tvshow.nfo` ou do nome da pasta), com validação da contagem aproximada de episódios. Suporte a override explícito em `series.toml` (`[metadata] anilist_id = 12345`). Se a busca for inconclusiva e não houver ID manual, o pipeline degrada graciosamente, operando sem metadados externos. | Usuário / Arquitetura |
| **D2** | **Escopo da Memória por Pasta de Série:** A memória (`characters.yaml`, `glossary.yaml`, `story.yaml`) é única por pasta de série raiz, mesmo quando a pasta contiver múltiplas temporadas (ex: *High School D×D* T1–T4). Isso unifica termos e personagens da 1ª à última temporada. | Usuário / Arquitetura |
| **D3** | **Fase 1 e Fase 2 no `translaterany run`:** O comando `run` executa automaticamente a Fase 1 (análise da série: `metadata` → `extract_terms` → `consolidate_memory`) antes de rodar a tradução da Fase 2 (`translate_dialogue` → `write` → `publish`). | Usuário / Arquitetura |
| **D4** | **Precedência Estrita de Edição:** `user` (edição manual no arquivo YAML) > `metadata` (AniList/Jikan) > `extracted` (IA). Se o usuário editar ou criar um termo no YAML, reexecuções nunca o sobrescrevem. | Roadmap / Design |
| **D5** | **Formato YAML Legível e Comentado:** Armazenamento via `ruamel.yaml` mantendo comentários e estrutura clara, permitindo edição humana direta com qualquer editor de texto. | Roadmap |
| **D6** | **Filtragem do Glossário por Episódio:** Na etapa `translate_dialogue`, apenas os termos que ocorrem no texto em inglês do episódio são injetados no prompt, reduzindo o consumo de tokens e preservando o cache de prefixo. | Roadmap / Desempenho |
| **D7** | **Rastreamento de Staleness (`retry --stale`):** O artefato de tradução grava o dicionário `used_terms: dict[str, str]` (termo → hash do conteúdo da entrada no glossário). Se o usuário alterar um termo no glossário, os episódios que continham aquele termo são detectados como desatualizados no comando `status` e têm seus registros resetados via `retry --stale` para reexecução pelo `run`. | Roadmap / Usabilidade |
| **D8** | **Comando CLI `memory`:** Adição do comando `translaterany memory <pasta>` para inspecionar termos, exportar/importar YAMLs e forçar atualização (`--refresh`). | Usabilidade |

---

## 5. Arquitetura e Modelagem de Dados

### 5.1 Estrutura de Arquivos da Memória

A memória da série é persistida em:
`<data_dir>/series/<series_key>/memory/`
e opcionalmente sincronizada/exportada para `<pasta_da_serie>/memory/` para fácil edição pelo usuário.

Arquivos gerados:
1. `characters.yaml`: Fichas dos personagens;
2. `glossary.yaml`: Dicionário de termos técnicos, jargões, locais, golpes e nomes;
3. `story.yaml`: Sinopse geral da série, sinopses por episódio, gêneros e tags.

### 5.2 Schemas Pydantic / Modelos

```python
# translaterany/memory/models.py
from enum import StrEnum
from pydantic import BaseModel, Field

class EntrySource(StrEnum):
    USER = "user"
    METADATA = "metadata"
    EXTRACTED = "extracted"

class CharacterRole(StrEnum):
    MAIN = "main"
    SUPPORTING = "supporting"
    BACKGROUND = "background"

class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"

class CharacterEntry(BaseModel):
    name: str                           # Nome ocidental/romanizado (ex: "Yuu Otosaka")
    native_name: str | None = None      # Nome original (ex: "乙坂 有宇")
    aliases: list[str] = Field(default_factory=list) # Apelidos (ex: ["Yuu", "Grim Reaper"])
    gender: Gender = Gender.UNKNOWN     # Gênero (AniList define com precisão)
    role: CharacterRole = CharacterRole.SUPPORTING
    speech_style: str | None = None     # Ex: "sarcástico, informal, autoconfiante"
    notes: str | None = None
    source: EntrySource = EntrySource.EXTRACTED

class GlossaryCategory(StrEnum):
    NAME = "name"           # Nomes de pessoas / entidades
    PLACE = "place"         # Cidades, escolas, reinos
    TECHNIQUE = "technique" # Golpes, habilidades, magias (ex: "Plunder", "Time Leap")
    OBJECT = "object"       # Itens específicos, artefatos
    ORGANIZATION = "org"    # Escolas, conselhos, facções
    GENERAL = "general"     # Gírias, conceitos do universo

class GlossaryEntry(BaseModel):
    term: str                           # Termo original em EN/JA (ex: "Hoshinoumi Academy")
    translation: str                    # Tradução oficial em PT-BR (ex: "Academia Hoshinoumi")
    category: GlossaryCategory = GlossaryCategory.GENERAL
    keep_original: bool = False         # Se True, não traduz (ex: nomes de golpes em inglês)
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None
    source: EntrySource = EntrySource.EXTRACTED

    def content_hash(self) -> str:
        """Hash do conteúdo relevante da entrada para detecção de staleness."""
        import hashlib
        data = f"{self.term}|{self.translation}|{self.category}|{self.keep_original}|{','.join(sorted(self.aliases))}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]

class EpisodeSynopsis(BaseModel):
    episode_key: str                    # Chave canônica do episódio (ex: "S01E01")
    number: int                         # Número sequencial absoluto ou da temporada
    title: str | None = None
    synopsis: str = ""

class StoryMemory(BaseModel):
    title: str
    romaji_title: str | None = None
    native_title: str | None = None
    year: int | None = None
    synopsis: str = ""
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    episodes: dict[str, EpisodeSynopsis] = Field(default_factory=dict) # Indexado por ep.key
```

### 5.3 Artefatos de Pipeline

```python
# translaterany/memory/artifacts.py
from pydantic import BaseModel, Field
from translaterany.memory.models import CharacterEntry, GlossaryEntry, StoryMemory

class MetadataArtifact(BaseModel):
    matched: bool
    anilist_id: int | None = None
    mal_id: int | None = None
    title: str = ""
    characters: list[CharacterEntry] = Field(default_factory=list)
    story: StoryMemory | None = None

class ExtractTermsArtifact(BaseModel):
    episode_key: str
    terms: list[GlossaryEntry] = Field(default_factory=list)
    character_mentions: list[str] = Field(default_factory=list)

class ConsolidatedMemoryArtifact(BaseModel):
    series_name: str
    characters_count: int
    glossary_count: int
    characters_hash: str
    glossary_hash: str
    story_hash: str
    glossary_terms: list[str] = Field(default_factory=list)
```

---

## 6. Fluxo de Execução no Pipeline

### 6.1 `DEFAULT_PIPELINE` Atualizado

A tupla completa do pipeline padrão em `src/translaterany/stages/__init__.py` passa a ser:

```python
DEFAULT_PIPELINE: tuple[str, ...] = (
    "inventory",            # episode: valida integridade e descobre faixas do arquivo
    "metadata",             # series: busca AniList + Jikan e gera metadata.json
    "select_track",         # episode: escolhe a faixa de legenda EN
    "extract",              # episode: extrai o .ass original do MKV
    "normalize",            # episode: separa tags inline e gera NormalizedDoc
    "classify",             # episode: classifica dialogue/sign/song
    "extract_terms",        # episode: extrai termos candidatos com IA
    "consolidate_memory",   # series: reduce das extrações e consolidação dos YAMLs
    "translate_dialogue",   # episode: traduz diálogos com glossário e personagens
    "write",                # episode: reconstitui ASS e injeta ; TranslaterAny
    "publish",              # episode: publica <video>.pt-BR.ass
    "remux",                # episode: opcional (desabilitado por padrão)
)
```

### 6.2 Detalhe das Etapas

1. **`MetadataStage` (`stages/metadata.py`):**
   - **Escopo:** `series`.
   - **Inputs:** `("inventory",)`.
   - Lê `SeriesConfig` (se houver `anilist_id` em `series.toml` sob `[metadata]`).
   - Se não houver override, usa `title` e `year` da série para buscar no AniList via `AniListClient`.
   - Consulta `idMal` correspondente no Jikan via `JikanClient` para obter títulos e sinopses por episódio.
   - Gera o artefato `metadata.json` (`MetadataArtifact`).
   - Se a rede estiver offline ou a busca falhar, grava artefato com `matched=False` e prossegue sem travar a execução.

2. **`ExtractTermsStage` (`stages/extract_terms.py`):**
   - **Escopo:** `episode`.
   - **Inputs:** `("metadata", "normalize")`.
   - Lê as falas do episódio em `NormalizedDoc` e o `MetadataArtifact` da série.
   - Envia lote de falas para o modelo de análise (`gemma4:12b` via `ctx.llm`):
     - Prompt instrui a identificar termos recorrentes não triviais: nomes próprios, apelidos, habilidades, lugares, organizações e jargões.
   - Produz artefato `extract_terms.json` (`ExtractTermsArtifact`).

3. **`ConsolidateMemoryStage` (`stages/consolidate_memory.py`):**
   - **Escopo:** `series`.
   - **Inputs:** `("metadata", "extract_terms")`.
   - Agrupa as listas de termos de todos os episódios da série (`ctx.inputs.json_all("extract_terms", ExtractTermsArtifact)`).
   - Combina com `MetadataArtifact` (personagens e títulos canônicos do AniList).
   - Executa consolidação via IA (ou fusão determinística com desempate semântico):
     - Unifica grafias e sinônimos;
     - Define a tradução oficial PT-BR para cada termo;
     - Determina o gênero e papel de cada personagem.
   - Lê os arquivos YAML pré-existentes (se o usuário já tiver editado algum) e aplica **precedência estrita**: campos marcados como `source: user` **nunca são alterados**.
   - Salva os arquivos atualizados `characters.yaml`, `glossary.yaml` e `story.yaml` em `<data_dir>/series/<key>/memory/`.
   - Grava via `ctx.output.json(...)` o artefato `consolidate_memory.json` (`ConsolidatedMemoryArtifact`).

4. **Integração na Etapa `StageTranslateDialogue` (M2):**
   - **Inputs:** `("normalize", "classify", "consolidate_memory")`.
   - Lê `glossary.yaml` e `characters.yaml`.
   - Filtra apenas os termos do glossário cujo `term` (ou `aliases`) ocorre nas falas em inglês do episódio.
   - Formata a seção `[GLOSSÁRIO OBRIGATÓRIO]` e `[PERSONAGENS]` no início do prompt do modelo de tradução:
     ```
     [GLOSSÁRIO OBRIGATÓRIO]
     - Hoshinoumi Academy -> Academia Hoshinoumi
     - Plunder -> Saque (habilidade)
     - Collapse -> Desmoronamento (habilidade)

     [PERSONAGENS PRESENTES]
     - Yuu Otosaka (Masc): protagonista, informal, sarcástico
     - Nao Tomori (Fem): líder do conselho, fala rápida, direta
     ```
   - Registra no artefato da etapa (`translate_dialogue.json`) o mapa `used_terms: dict[str, str]` (termo → `content_hash()`).

---

## 7. Integração no CLI e Invalidação por Staleness

### 7.1 Novo Comando `translaterany memory`

```bash
translaterany memory <pasta> [OPÇÕES]
```
- Exibe tabela resumida dos termos do glossário, categorias e contagem de personagens;
- Opções:
  - `--export <destino>`: Copia os YAMLs para uma pasta local para edição facilitada;
  - `--import <origem>`: Carrega termos editados externamente pelo usuário;
  - `--refresh`: Força reconsulta ao AniList e Jikan ignorando o cache em disco.

### 7.2 Invalidação com `translaterany retry --stale`

- Quando o usuário edita `glossary.yaml` (ex.: alterou a tradução de um termo de *"Pilhar"* para *"Saque"*):
- O comando `translaterany status` inspeciona os episódios: para cada um, lê `used_terms` de `translate_dialogue.json` e compara com o hash atual daquele termo no `glossary.yaml`.
- Se houver divergência, marca o episódio como `desatualizado (glossário modificado)`.
- O comando `translaterany retry <pasta> --stale` reseta os manifests de `translate_dialogue`, `write` e `publish` para esses episódios afetados, instruindo o usuário a rodar `translaterany run`, que reexecutará apenas os episódios desatualizados mantendo os demais 100% em cache.

---

## 8. Estratégia de Testes Automatizados (100% Sintéticos)

Todos os testes com `pytest` rodam sem acesso à rede externa e sem depender do Ollama ativo:
1. `test_anilist_client.py`: Testa cliente GraphQL com mock de respostas de busca por título e consultas de personagens (sucesso, ambiguidade, offline e rate limiting).
2. `test_jikan_client.py`: Testa cliente REST mockando sinopses por episódio do Jikan e cache local.
3. `test_memory_yaml.py`: Testa leitura e gravação segura com `ruamel.yaml`, preservação de comentários, idempotência e precedência de edições de usuário (`source: user`).
4. `test_stage_metadata.py`: Testa execução da etapa `metadata` com dados mockados e comportamento quando offline/sem match.
5. `test_stage_extract_terms.py`: Testa extração de termos por episódio usando `FakeLLM`.
6. `test_stage_consolidate_memory.py`: Testa consolidação reduce de múltiplos episódios, gravação dos YAMLs e artefato `consolidate_memory.json`.
7. `test_translate_with_glossary.py`: Testa que `StageTranslateDialogue` injeta corretamente os termos do glossário e que a tradução é padronizada.
8. `test_stale_invalidation.py`: Testa detecção de episódios desatualizados ao modificar `glossary.yaml` e reprocessamento com `retry --stale`.
