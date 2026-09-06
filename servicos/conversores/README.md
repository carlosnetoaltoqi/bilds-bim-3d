# servicos/conversores — peças e formatos (:4300)

Contexto **conversores** (docs/arquitetura.md, ADR-013). Conversões síncronas, de segundos, sem fila e
**sem estado** (sem Mongo, sem storage, sem `@bim/dominio`): o arquivo enviado é apagado ao fim e o
resultado volta no corpo da resposta. Tudo é a biblioteca `bim_pipeline` pela `Biblioteca` de `@bim/base`.

| Rota | O quê |
|---|---|
| `POST /tesselar` (multipart `file` + `deflexao?`) | `.stp`/`.step`/`.igs`/`.iges`/`.ifc` → `{pos, col, idx, partes, unidade, bbox_mm, formato, volume_cm3?, costurado?, …}` (contrato `geometria`) |
| `POST /aq` (JSON `{info, partes[] \| pos,col,idx}`) | → download `.aq` de uma peça (`application/x-sqlite3`); resumo em `X-Aq-Resumo` |
| `POST /plugin/inspecionar` (multipart `file` = DLL) | plugin de CAD que é casca de um catálogo web → `{host, hosts, plugin, versao, titulo, categorias[]}` (contrato `info-plugin`) |
| `GET /health` | `{status, servico, biblioteca}` |

Subir: `pnpm dev:conversores` (raiz) ou `pnpm --filter conversores start` após `pnpm -r build`.
Variáveis: `CONVERSORES_PORT` (4300), `WEB_ORIGIN`, `BIBLIOTECA_DIR`, `PYTHON`. STEP/IGES/IFC exigem
`pip install -e 'biblioteca[cad]'` (OpenCASCADE, ifcopenshell). Para portar: este diretório +
`pacotes/base` + `biblioteca/`.
