# servicos/editor-de-pecas — edição de peças (:4400)

Contexto **editor de peças** (docs/arquitetura.md, ADR-014). Só as ESCRITAS de edição; a leitura de
catálogo, produto e geometria é da API de catálogo (:4000). Serviço com dados: importa `@bim/dominio`
e escreve nas mesmas coleções e no mesmo storage que o criador e a API (acoplamento aceito da POC,
docs/arquitetura.md §5).

| Rota | O quê |
|---|---|
| `PATCH /produtos/:id` | nome, serie, specs, curva, potencia, conexoes (só os presentes); primeira edição guarda `infoOriginal`; série nova recomputa os filtros do catálogo |
| `PUT /geometrias/:id` | `{pos,col,idx}` editado. Geometria exclusiva → `.orig.json` na primeira escrita; compartilhada → **copy-on-write** (`geo/<importId>/<productId>.json`, `geoKeyCompartilhada`) — os irmãos não mudam (ADR-005). Pede a miniatura ao criador (`POST /miniaturas/regerar`); sem resposta, `thumbErro` e `miniatura: 'nao-solicitada'` |
| `POST /geometrias/:id/restaurar` | desfaz: volta ao compartilhado e apaga a cópia, ou repõe o `.orig.json` |
| `GET /geometrias/:id/original` | o JSON como veio do `.aq` (compartilhado → `.orig` → o vivo) |
| `GET /health` | 200/503 pela conexão do Mongoose |

Subir: `pnpm dev:editor` (raiz). Variáveis: `EDITOR_PORT` (4400), `MONGODB_URI`, `MONGODB_DB`,
`STORAGE_PATH`, `CRIADOR_URL` (padrão http://localhost:4100), `WEB_ORIGIN`, `JSON_BODY_LIMIT`. Para
portar: este diretório + `pacotes/base` + `pacotes/dominio` + `web/src/components/bim-editor`.
