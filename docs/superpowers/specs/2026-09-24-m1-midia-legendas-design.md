# M1 — Mídia e legendas · Design

- **Marco:** M1 (ver [`ROADMAP.md`](../../../ROADMAP.md))
- **Data:** 2026-09-24
- **Status:** rascunho para revisão
- **Depende de:** M0 ([spec](2026-09-24-m0-fundacao-design.md))

---

## 1. Objetivo

Tirar a legenda certa de cada MKV, entender a estrutura dela (tipos de linha, textos únicos, cenas) e gravá-la de volta **sem perder nada** — e, quando houver tradução (a partir do M2), publicá-la ao lado do vídeo e/ou reinseri-la no MKV com segurança.

Ao fim do M1 **não existe tradução**. O pipeline produz, para cada episódio, um `.ass` no diretório de dados **idêntico byte a byte** ao extraído, mais os artefatos estruturais que as etapas de IA do M2–M4 vão consumir.

## 2. Fora do escopo

| Item | Onde |
|---|---|
| Tradução e qualquer IA | M2 |
| Classificação por IA de linhas ambíguas | M4 |
| Metadados AniList/Jikan | M3 |
| Refazer quebras de linha / velocidade de leitura | M7 |
| OCR de legendas em imagem (PGS/VobSub) | pós-v1 |
| Mesclar faixas de diálogo e de placas realmente separadas | pós-v1 (não ocorre nos casos de teste — ver §6.4) |

## 3. Evidências dos casos de teste

Medições estruturais feitas nas faixas reais (sem ler falas):

| Achado | Implicação |
|---|---|
| *Charlotte*: `Dialog - ENG` **contém** a `S&S` (mesmos 6.715 eventos posicionados, 95% dos inícios coincidem) | uma faixa basta; não há faixas divididas nos casos de teste |
| *Charlotte* S01E01: ~7.100 eventos, **515 textos únicos** (374 de diálogo); *D×D* T4: ~8.000 eventos, 454 únicos | agrupar por texto único é essencial |
| Especiais do *D×D*: duas `Full` de grupos diferentes (CBM `default`, ADZ), 55–85% de coincidência | são traduções diferentes; escolher uma |
| *D×D* S00E18: `S&S` é a faixa `default`, `Full` não | "preferir `default`" sozinho erra |
| Estilos `*Romaji*`/`*Rom*`/`* Ro *` ao lado de `*English*`/`*Eng*` | romaji não se traduz |
| `pysubs2` descarta `[Aegisub Extradata]` e reescreve cabeçalho/estilos | parser próprio (abordagem A) |
| Após remux, a faixa EN extraída é **idêntica**; a faixa inserida volta com os mesmos eventos, seções e comentários (difere só em uma linha em branco final); duração varia ~7 ms | o remux não invalida o cache do texto; idempotência por impressão digital registrada |
| Saída de texto do `mkvmerge` é localizada ("ID da faixa") | ler metadados só por `mkvmerge -J` |
| Os dois `tvshow.nfo` têm `<tvdbid>` | identidade estável da série |

## 4. Decisões (revisar)

| # | Decisão | Origem |
|---|---|---|
| D1 | **Abordagem A**: `.ass` guardado em bytes; parser próprio orientado a linhas; a gravação altera **somente** o campo de texto dos eventos mudados | usuário |
| D2 | Publicar na biblioteca **só quando houver tradução**; no M1 nada é escrito na biblioteca | usuário |
| D3 | Remux **substitui** o original após verificação, troca atômica, **sem backup** por padrão (`keep_backup` opcional) | usuário |
| D4 | MKV final: PT-BR **default**; faixas **SDH/CC removidas**; demais legendas mantidas **sem default** | usuário |
| D5 | Faixa-base: `Full`/`Dialog` > demais > `S&S` (S&S só se for a única); **SDH nunca**; desempate `default` > menor ID | usuário |
| D6 | Episódio múltiplo no formato **`S01E01-02`** | usuário |
| D7 | Escolha manual por série via `series.toml` opcional (faixa e mapeamento de estilos) | usuário |
| D8 | Parser próprio de `SxxEyy` (sem `guessit`) | nomenclatura Sonarr é padronizada |
| D9 | Identidade da série: `slug(nome) + hash(tvdbid > tmdbid > imdb_id do tvshow.nfo)`; sem `.nfo`, hash do caminho absoluto | corrige limitação do M0 |
| D10 | Marca de autoria: comentário `; TranslaterAny` no cabeçalho do `.ass` e nome de faixa `Português (Brasil) — TranslaterAny` | distinguir o que é da app do que é de terceiros |
| D11 | A marca no `.ass` **é** o sinal de "texto traduzido": `write` só a insere quando a fonte do texto é uma etapa de tradução; `publish`/`remux` só agem se ela existir | trava D2 autocontida, sem acoplamento entre etapas |
| D12 | Dependências novas: `pysubs2` (apenas conversão SRT→ASS) e `charset-normalizer` | |

## 5. Mudanças no núcleo (M0)

| Mudança | Motivo |
|---|---|
| **Entradas por instância**: `Stage.inputs` pode ser definido no `__init__` a partir das opções; o validador do config passa a checar `instance.inputs` | `write` lê a etapa indicada em `text_source` |
| Atributo `translates: ClassVar[bool] = False` em `Stage` | `write` sabe se a fonte do texto é tradução |
| Gancho `Stage.verify_cached(ctx, artifact_path) -> bool` (padrão `True`), chamado num *cache hit*; `False` ⇒ reexecuta | `publish`/`remux` produzem coisas fora do diretório de dados |
| `StageContext.previous_output: Path \| None` — artefato anterior da própria etapa para a unidade, se houver | idempotência do remux |
| `StageContext.force: bool` e `run --force`: reabre episódios `skipped` no início e permite sobrescrever PT-BR de terceiros; **não** entra na chave de cache | §12, §13 |
| `units.discover` substituída por `library.discover` (§6) | descoberta real |
| Chave da série muda (D9) | dados do M0 ficam órfãos; sem usuários ainda — aceito |
| `status`: "pasta nunca processada" em vez de tabela vazia; episódio cujo arquivo sumiu marcado "(arquivo ausente)" | menores adiados do M0 no mesmo código |

## 6. Descoberta (`library/`)

### 6.1 Série ou biblioteca
`run <pasta>`: a pasta é **uma série** se contiver `tvshow.nfo`, subpastas `Season N`/`Specials`, ou `.mkv` diretamente; caso contrário, **cada subpasta** é avaliada como série (um nível). Arquivos `*.mkv`/`*.MKV` (sem diferenciar maiúsculas).

### 6.2 Episódios
- Regex (sem diferenciar maiúsculas): `S(\d{1,2})E(\d{1,3})(?:-(\d{1,3}))?` → chave normalizada `S01E04` ou `S01E01-02` (temporada com 2 dígitos, episódio com ao menos 2).
- Sem correspondência: chave = slug do nome do arquivo; aviso no terminal.
- **Duas mídias com a mesma chave**: ambas **ignoradas nesta execução** com aviso listando os arquivos (não viram unidades).
- **Arquivo recente** (modificado há menos de `discovery.min_file_age`, padrão 120 s): ignorado nesta execução, com aviso.
- O resumo do `run` lista os ignorados.

### 6.3 Identidade da série (D9)
Lê `tvshow.nfo` (XML simples) procurando `<tvdbid>`, depois `<tmdbid>`, depois `<imdb_id>`. Chave = base do `slugify(nome)` + `-` + `sha256("tvdb:289679")[:6]` (sem `.nfo`: `sha256("path:<caminho absoluto>")[:6]`). `.nfo` ilegível ⇒ trata como ausente, com aviso.

### 6.4 `series.toml` (opcional, na pasta da série; a app só lê)
```toml
[subtitles]
track = "ADZ"               # parte do nome da faixa a preferir

[styles]                    # corrige a classificação por estilo
"Mirror" = "sign"
"GJM_Main" = "dialogue"
```
Valores de `[styles]`: `dialogue`, `sign`, `song`, `romaji`, `karaoke`, `drawing`, `comment`. Arquivo inválido ⇒ falha da série com mensagem clara. A seção `[metadata]` será acrescentada no M3.

## 7. Seleção de faixa (`select_track`, escopo episódio, `reads_source`)

Lê `mkvmerge -J` do MKV.

1. **Candidatas:** legendas com `text_subtitles: true` e `codec_id` `S_TEXT/ASS`, `S_TEXT/SSA` ou `S_TEXT/UTF8` (SRT), com idioma (`language_ietf`, senão `language`) `en`/`eng` ou `und`. Legendas em imagem: `codec_id` `S_HDMV/PGS` ou `S_VOBSUB`.
2. **Descartes com motivo:**
   - SDH/CC — nome contém `SDH`, `CC` (palavra isolada) ou `hearing` (sem diferenciar maiúsculas), ou propriedade `flag_hearing_impaired: true` (só aparece quando marcada): **nunca** base; IDs guardados para o remux.
   - Faixa da própria app (nome com `TranslaterAny`): ignorada.
3. **PT-BR de terceiros:** faixa com idioma `pt`/`por`/`pt-BR` que **não** seja da app, ou `<vídeo>.pt-BR.ass` ao lado sem a marca D10 ⇒ `SkipEpisode("já existe legenda PT-BR de outra fonte")`, exceto com `--force`.
4. **Só legenda em imagem** (PGS/VobSub) ⇒ `SkipEpisode("legenda em imagem (OCR fora da v1)")`. Nenhuma candidata ⇒ `SkipEpisode("sem legenda em inglês")`. Só SDH ⇒ `SkipEpisode("só há legenda SDH")`.
5. **Ordem de preferência:** override do `series.toml` (se casar com alguma candidata; se não casar, aviso e segue) > faixas que **não** são de placas/músicas (nome contém `sign`, `song`, `S&S`, `forced` ou flag `forced`) > `default` > menor ID.
6. **Artefato** `select_track.json`:
```json
{
  "chosen": {"id": 4, "codec": "SubStationAlpha", "language": "en", "name": "Dialog - ENG", "default": false, "forced": false},
  "reason": "faixa completa (não é de placas/músicas)",
  "candidates": [{"id": 3, "name": "S&S", "kind": "signs_songs", "discarded": "preterida: placas/músicas"}],
  "sdh_track_ids": [],
  "own_track_ids": [],
  "attachments": [{"id": 1, "file_name": "font.ttf", "content_type": "font/ttf"}]
}
```
`doctor_checks`: `mkvmerge` presente (mostra a versão).

## 8. Extração (`extract`, escopo episódio, `reads_source`, entrada `select_track`)

- `mkvextract <mkv> tracks <id>:<tmp>`; o artefato `extract.ass` são os **bytes** extraídos.
- SRT: detecta codificação (UTF-8/BOM, senão `charset-normalizer`), converte para ASS com `pysubs2` e grava o ASS resultante.
- Faixa `und`: verifica se o texto parece inglês — ≥ 15% das palavras dos eventos com texto pertencem a uma lista fixa das ~100 palavras mais comuns do inglês; senão `SkipEpisode("faixa 'und' não parece inglês")`.
- `doctor_checks`: `mkvextract` presente.

## 9. Parser e documento ASS (`subtitles/ass.py`)

### 9.1 Leitura
- Entrada: bytes. Detecta BOM UTF-8 e quebra de linha predominante (`\n`/`\r\n`); decodifica UTF-8 (erro ⇒ "ASS malformado: não é UTF-8").
- Divide em linhas preservando os terminadores. Localiza `[Events]` (sem diferenciar maiúsculas) e a primeira linha `Format:` dentro dela; colunas separadas por vírgula, com espaços removidos. Exige a coluna `Text` **por último**.
- Cada linha `Dialogue:`/`Comment:` em `[Events]`: separa o valor em `len(format) - 1` vírgulas (`maxsplit`), o restante é o texto (pode conter vírgulas).
- Tempos `H:MM:SS.cc` → milissegundos.
- Erros: sem `[Events]`, sem `Format:`, `Text` fora da última posição, linha de evento com campos a menos ⇒ `AssError` com o número da linha.

### 9.2 Modelo
```python
@dataclass(frozen=True)
class AssEvent:
    index: int          # ordem entre os eventos
    line_no: int        # linha no arquivo (0-based)
    kind: Literal["dialogue", "comment"]
    fields: dict[str, str]   # colunas do Format, exceto Text (Layer, Start, End, Style, Name, ...)
    text: str
```
`AssDocument` guarda as linhas originais (com terminadores), os eventos e metadados (`bom`, `newline`, `format`).

### 9.3 Gravação
`render(doc, new_texts: dict[int, str], marker: bool) -> bytes`:
- Para cada evento em `new_texts` cujo texto difere, reconstrói **só aquela linha**: prefixo original da linha até o início do campo de texto + novo texto + terminador original.
- `marker=True`: insere a linha `; TranslaterAny` logo após `[Script Info]` (uma única vez; se já existir, não duplica).
- Demais linhas: bytes originais. Invariante testado: `render(doc, {}, False) == bytes originais`.

## 10. Normalização (`normalize`, entrada `extract`)

### 10.1 Segmentação de texto (`subtitles/segments.py`)
- Tokeniza em blocos `{...}` e texto.
- **Prefixo**: blocos antes do primeiro texto; **sufixo**: blocos após o último texto; **internos**: blocos entre textos ⇒ marcadores `⟦1⟧`, `⟦2⟧`…
- `\N`, `\n`, `\h` permanecem no texto.
- **Modo desenho**: texto emitido enquanto `\p<n>` (n ≥ 1) está ativo é vetor, não texto ⇒ o evento é marcado `drawing`.
- Invariante: `prefix + fill(text, markers) + suffix == texto original` (verificado para todo evento; violação ⇒ falha com o índice).

### 10.2 Unidades de texto único
Chave = `(estilo, texto limpo normalizado, nº de marcadores)`, onde "texto limpo" é o texto com marcadores e espaços colapsados. Cada unidade guarda os eventos que a usam. Eventos `comment`, vazios ou só de desenho não formam unidade traduzível (ficam com `unit: null`).

### 10.3 Cenas
Eventos de diálogo candidatos (não `comment`/`drawing`), em ordem de início, agrupados enquanto o intervalo até o próximo for ≤ `scene_gap_ms` (opção, padrão 5000).

### 10.4 Artefato `normalize.json`
```json
{
  "encoding": {"bom": false, "newline": "\n"},
  "format": ["Layer", "Start", "End", "Style", "Name", "MarginL", "MarginR", "MarginV", "Effect", "Text"],
  "events": [{"index": 0, "line_no": 42, "kind": "dialogue", "style": "Default", "start_ms": 1000, "end_ms": 3000,
              "layer": 0, "name": "", "prefix": "{\\an8}", "text": "Hello ⟦1⟧world", "markers": ["{\\i1}"],
              "suffix": "", "drawing": false, "unit": "u12"}],
  "units": [{"id": "u12", "style": "Default", "text": "Hello ⟦1⟧world", "markers": 1, "events": [0, 57]}],
  "scenes": [{"id": "s1", "start_ms": 1000, "end_ms": 9000, "events": [0, 1, 2]}]
}
```

## 11. Classificação (`classify`, entrada `normalize`)

### 11.1 Tipos e regras (em ordem)
| Tipo | Regra | Traduzível |
|---|---|---|
| `comment` | evento `Comment:` | não |
| `drawing` | só desenho vetorial | não |
| `karaoke` | algum evento da unidade tem `\k`, `\kf`, `\ko` ou `\K` | não |
| `romaji` | tokens do estilo contêm `rom`, `romaji` ou `ro` | não |
| `song` | tokens do estilo contêm `op`, `ed`, `in`/`in<n>`, `ins`, `insert`, `song`, `lyric(s)`, `opening`, `ending`, `karaoke` | sim (M4) |
| `sign` | tokens do estilo contêm `sign(s)`, `ts`, `typeset`, `title`, `card`, `note`, `screen`, **ou** algum evento tem `\pos`/`\move` e o estilo não é o principal | sim (M4) |
| `dialogue` | demais | sim |

- **Tokens do estilo**: nome dividido em não alfanuméricos e em fronteiras *camelCase* (`CharlotteEDEnglish` → `charlotte`, `ed`, `english`; `OP - Romaji 2` → `op`, `romaji`, `2`), em minúsculas.
- **Estilo principal**: entre as unidades que sobram para `dialogue`/`sign` sem regra de estilo, o estilo com mais unidades.
- `uncertain = true` quando mais de uma regra de estilo casa (ex.: `op` e `sign`) ou quando só a regra de `\pos` decidiu. No M1, `uncertain` é informativo.
- `series.toml [styles]` tem precedência sobre as regras.

### 11.2 Artefato `classify.json`
```json
{"main_style": "GJM_Main",
 "units": {"u12": {"type": "dialogue", "uncertain": false, "rule": "padrão"}},
 "counts": {"dialogue": 374, "sign": 58, "song": 30, "romaji": 59}}
```

## 12. Gravação e publicação

### 12.1 Contrato de texto
Toda etapa que produz texto grava `UnitTexts`: `{"texts": {"<unit_id>": "<texto com marcadores>"}}`. Unidades ausentes mantêm o texto original.

### 12.2 `write` (entradas `extract`, `normalize` e a de `text_source`)
- Opção `text_source` (padrão `"normalize"` = texto original).
- Monta `new_texts` por evento: `prefix + fill(texto da unidade, markers do evento) + suffix`.
- Chama `render(doc, new_texts, marker = REGISTRY.get(text_source).translates)`.
- Artefato `write.ass`. No M1 (`text_source = "normalize"`): **idêntico** a `extract.ass`.
- Erro se um texto de tradução não tiver exatamente os marcadores `⟦1⟧…⟦n⟧` da unidade (mensagem com a unidade) — proteção para o M2.

### 12.3 `publish` (entrada `write`; destino a partir de `ctx.episode.source`)
- Se `write.ass` **não** contém a marca D10 ⇒ artefato `{"published": false, "reason": "pipeline sem tradução"}`; nada é escrito.
- Destino: `<pasta do vídeo>/<nome do vídeo sem extensão>.pt-BR.ass`.
- Destino existente **sem** a marca ⇒ `SkipEpisode("já existe .pt-BR.ass de outra fonte")`, exceto com `force`.
- Escrita atômica com temporário oculto na mesma pasta (`.<nome>.translaterany-tmp`).
- Sem permissão ⇒ falha com "não foi possível gravar em <destino>; a legenda está em <write.ass>".
- Artefato `{"published": true, "path": "...", "sha256": "..."}`; `verify_cached`: arquivo existe e hash confere.

## 13. Remux (`remux`, entradas `write`, `select_track`, `reads_source`; desligado por padrão)

### 13.1 Opções
```toml
[stages.remux]
enabled = false
[stages.remux.options]
keep_backup = false
remove_sdh = true
```

### 13.2 Fluxo
1. `write.ass` sem a marca ⇒ `{"status": "not_translated"}`.
2. **Idempotência**: se `ctx.previous_output` registra `mkv_fingerprint_after` igual à impressão digital atual **e** `ass_sha256` igual ao hash atual de `write.ass` ⇒ `{"status": "up_to_date", ...}` (mesmo conteúdo do anterior); nada é tocado.
3. **Espaço**: livre no disco do MKV ≥ tamanho do MKV × 1,05; senão falha "sem espaço para o remux (precisa de X GB)".
4. Comando (`mkvmerge -o <tmp oculto na mesma pasta>`):
   - `--subtitle-tracks '!<ids>'` com os SDH (se `remove_sdh`) e as faixas da própria app;
   - `--default-track-flag <id>:no` para cada legenda mantida;
   - arquivo `write.ass` com `--language 0:pt-BR --track-name "0:Português (Brasil) — TranslaterAny" --default-track-flag 0:yes`.
   - Código de saída 0 ou 1 (avisos, registrados no log) aceito; 2 ⇒ falha.
5. **Verificação** com `mkvmerge -J` do temporário: nº de faixas = original − removidas + 1; duração dentro de ±1 s; nº de anexos igual; existe faixa `pt-BR` da app marcada `default`; nenhuma outra legenda `default`. Falha ⇒ apaga o temporário e falha a unidade.
6. `keep_backup` ⇒ `os.replace(original, original + ".bak")` antes; depois `os.replace(tmp, original)`.
7. Artefato: `{"status": "remuxed", "mkv_fingerprint_after": "...", "ass_sha256": "...", "removed_track_ids": [...], "backup": null}`.
8. `verify_cached`: status `remuxed`/`up_to_date` ⇒ impressão digital atual do MKV igual a `mkv_fingerprint_after`; `not_translated` ⇒ `True`.

### 13.3 Por que não entra em laço
Após o remux a impressão digital muda ⇒ `inventory`, `select_track`, `extract` reexecutam; `select_track` ignora a faixa da app e escolhe a mesma EN; o `extract` sai **idêntico** (medido, §3) ⇒ `normalize`…`write` em cache; `remux` reexecuta (entrada `select_track` mudou: IDs), encontra o estado registrado e responde `up_to_date`. A execução seguinte fica inteira em cache.

## 14. Configuração nova

```toml
[discovery]
min_file_age = 120          # segundos

[pipeline]
stages = ["inventory", "select_track", "extract", "normalize", "classify", "write", "publish", "remux"]

[stages.normalize.options]
scene_gap_ms = 5000

[stages.write.options]
text_source = "normalize"
```
Pipeline padrão do M1: o acima, com `remux` desabilitado.

## 15. CLI

- `run <pasta>`: série ou biblioteca (§6.1); com biblioteca, processa as séries em sequência, cada uma com seu lock; o resumo final agrega por série e lista arquivos ignorados.
- `run --force`: ver §5.
- `status`: mostra, por episódio, a faixa escolhida (nome) e o motivo de pulo; mensagens de §5.
- `retry` e `doctor`: sem mudança de interface.

## 16. Erros

| Caso | Tratamento |
|---|---|
| `mkvmerge`/`mkvextract` ausentes | `doctor` ❌ ⇒ `run` não começa (código 2) |
| MKV ilegível (`mkvmerge -J` falha) | unidade `failed`: "MKV ilegível: <1ª linha do erro>" |
| Faixa `und` não inglesa | `skipped` com motivo |
| SRT com codificação estranha | detectada; se impossível decodificar ⇒ `failed` |
| ASS malformado | `failed`: "ASS malformado: <o que falta> (linha N)" |
| Invariante de segmentação violado | `failed` com o índice do evento (bug do parser — nunca grava algo diferente) |
| Arquivo recente / duplicado | ignorado nesta execução, com aviso |
| PT-BR de terceiros | `skipped`; `--force` sobrescreve |
| Biblioteca somente leitura | `publish`/`remux` `failed` com o caminho do `write.ass` |
| Sem espaço para remux | `failed` (tenta de novo no próximo `run`) |
| Verificação do remux falha | temporário apagado, original intacto, `failed` |
| `series.toml` inválido | série `failed` com mensagem clara |

## 17. Testes

Sem conteúdo real de legenda no repositório; textos inventados.

| Área | Casos |
|---|---|
| Parser | vírgulas no texto; CRLF; BOM; `Comment:`; `Format` com ordem não padrão; `[Aegisub Extradata]` e `[Aegisub Project Garbage]` preservados; ida e volta **byte a byte**; erros com número da linha |
| Segmentação | prefixo/sufixo/internos; `\N`; desenho `\p1…\p0`; karaokê; invariante de remontagem |
| Unidades | cópias quadro a quadro com `\pos` diferentes ⇒ 1 unidade; mesmo texto em estilos diferentes ⇒ 2; nº de marcadores diferente ⇒ 2 |
| Classificação | nomes de estilo reais (`CharlotteEDRomaji`, `CharlotteEDEnglish`, `OP - Romaji 2`, `ED Ro Blue`, `Sign-1`, `PikminimanSigns`, `SIGNS =`, `Tensai_Main`, `GJM_Main`, `Mirror`) com textos inventados; `series.toml [styles]`; `uncertain` |
| Seleção | JSONs no formato `mkvmerge -J` montados à mão para: *Charlotte* (S&S + Dialog), *D×D* (Full + S&S), especiais (2× Full, CBM default), S00E18 (S&S default), só SDH, só S&S, só PGS, `und`, faixa da app, PT-BR de terceiros, override `series.toml` |
| Descoberta | `S01E01`, `S01E01-02`, `S00E02`, sem padrão, `.MKV`, duplicatas, arquivo recente, série vs biblioteca, identidade por `.nfo` e por caminho |
| Integração (ffmpeg + mkvtoolnix; pulados se ausentes) | MKV sintético de 1 s com faixas `.ass` inventadas (`Full`, `Signs & Songs`, SDH) e uma fonte anexada ⇒ `select_track`→`extract`→`normalize`→`classify`→`write` idêntico; com uma etapa de tradução **falsa (só nos testes)**: `publish` grava ao lado, `remux` produz PT-BR default sem SDH, anexos preservados |
| Laço do remux | três execuções: a 2ª registra `up_to_date` sem alterar o MKV; a 3ª 100% em cache |
| Segurança do remux | verificação falha (simulada) ⇒ original intacto, temporário removido; `keep_backup` |
| Publicação | destino de terceiros ⇒ skip; `--force` sobrescreve; `verify_cached` refaz se o arquivo publicado for apagado |

## 18. Critérios de pronto

1. `uv run pytest -q` e `ruff` limpos.
2. `run` em *Charlotte (2015)* e *High School D×D (2012)* completa os **79** episódios sem falhas; faixas escolhidas conforme a tabela:

| Episódios | Escolha |
|---|---|
| *Charlotte* (todos) | `Dialog - ENG` |
| *D×D* T1–T4 | `Full Subtitle (...)` |
| *D×D* S00E11–S00E17 | `Full Subtitle (CBM/IK)` |
| *D×D* S00E18 | `Full Subtitle (Tensai/IK)` |

3. Para os 79 episódios, `write.ass` é **idêntico byte a byte** a `extract.ass`.
4. `classify` no *Charlotte* S01E01: estilo principal `GJM_Main`; unidades de diálogo na ordem de 370–380; romaji e karaokê não marcados como traduzíveis.
5. **Nenhum arquivo criado ou alterado em `temporada-teste/`** (verificado comparando listagem + mtimes antes/depois).
6. Segunda execução: tudo em cache.

## 19. Pontos de extensão

| Ponto | Quem usa |
|---|---|
| Contrato `UnitTexts` + `text_source` | M2 (`translate_dialogue`) e todas as etapas de texto seguintes |
| `translates` / marca D10 | M2 libera `publish`/`remux` |
| `classify.units[*].uncertain` | M4 (classificação por IA) |
| `normalize.scenes` | M4 (análise de cena) |
| `series.toml` | M3 (`[metadata] anilist_id`) |
| `verify_cached`, `previous_output`, `force` | etapas futuras com efeitos externos ou incrementais |
