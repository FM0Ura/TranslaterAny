# TranslaterAny

Tradução automática de legendas de anime (EN → PT-BR) com IA **local-first**, em um pipeline de múltiplas etapas focado em qualidade e fluidez.

## Pré-requisitos

- **Python 3.14+** (gerenciado via [`uv`](https://github.com/astral-sh/uv))
- **MKVToolNix** (`mkvmerge`, `mkvextract`)
- **Ollama** com os modelos recomendados:
  - `translategemma:12b` (tradução principal)
  - `gemma4:12b` (extração, análise de cena, revisão de sentido, coloquialidade, adaptação, leitura corrida e QA)
- **LanguageTool** (para a etapa de correção ortográfica determinística)

## LanguageTool (Docker Compose)

O projeto inclui um `docker-compose.yml` pronto e otimizado usando uma imagem leve do LanguageTool (`meyay/languagetool:latest`, ~300 MB) exposto na porta local padrão `8010`:

```bash
# Iniciar o LanguageTool em segundo plano
docker compose up -d

# Visualizar logs
docker compose logs -f

# Parar o serviço
docker compose down
```

## Diagnóstico do Ambiente

Para validar se todas as ferramentas, portas e modelos locais estão prontos:

```bash
uv run translaterany doctor
```

## Execução Básica

```bash
# Processar uma série / temporada
uv run translaterany run "/caminho/para/Serie (Ano)"

# Inspecionar estimativa de tokens e tempo
uv run translaterany estimate "/caminho/para/Serie (Ano)"
```
