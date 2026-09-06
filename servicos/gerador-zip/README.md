# servicos/gerador-zip — `.aq` → ZIP da bilds.com (:4200)

Contexto **gerador de ZIP** (docs/arquitetura.md, ADR-012). Recebe uma biblioteca `.aq` (ou o `.zip`
dela) e devolve, em stream, o ZIP no formato que a bilds.com consome
(`docs/conhecimento/zip-bilds-formato.md`). **Stateless:** sem Mongo, sem storage, sem `@bim/dominio`;
upload e ZIP são temporários e apagados. Consome as mesmas funções do criador de catálogos
(`bim_pipeline`: catálogo em memória, miniaturas, escritor do ZIP) pela `Biblioteca` de `@bim/base`.

| Rota | O quê |
|---|---|
| `POST /zip` (multipart `file`) | `.aq`/`.zip` → `200` `application/zip`, `Content-Disposition: <nome>-bilds.zip`. `400` extensão errada; `500` com o stderr da biblioteca (catálogo vazio). Miniatura que falha não aborta (`thumbCount: 0`) |
| `GET /health` | `{status, servico, biblioteca}` |

Subir: `pnpm dev:zip` (raiz) ou `pnpm --filter gerador-zip start` após `pnpm -r build`. Variáveis:
`ZIP_PORT` (4200), `WEB_ORIGIN`, `BIBLIOTECA_DIR`, `PYTHON`. Para portar: este diretório + `pacotes/base` + `biblioteca/`.

Um `.aq` grande leva o tempo do build (dezenas de segundos a minutos); não há fila.
