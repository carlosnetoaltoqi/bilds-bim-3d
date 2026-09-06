# servicos/criador-de-catalogos — importar e publicar catálogos (:4100)

Contexto **criador de catálogos** (docs/arquitetura.md, ADR-003/005/006). Recebe uma biblioteca `.aq`/`.zip`,
uma peça CAD ou a DLL de um plugin de CAD, roda a biblioteca Python (`bim_pipeline`) e o Chromium como
processos filhos e **publica** catálogo e produtos no Mongo, geometria e miniaturas no storage. É o dono
de `bim_imports`, `bim_catalogs` e `bim_products` na publicação (docs/arquitetura.md §5). Também exporta
um catálogo salvo como `.aq` novo. Não serve páginas nem geometria (API de catálogo) nem edita (editor).

| Rota | O quê |
|---|---|
| `POST /importacoes` (multipart `file` + `empresa?`; peça CAD: `fabricante?`, `catalogo?`, `nome?`, `deflexao?`) | `.aq`/`.zip` → biblioteca; `.stp`/`.step`/`.igs`/`.iges`/`.ifc` → peça CAD num catálogo "Peças STEP/IFC". **202** `{importId, tipo, status:'recebido', statusUrl}` |
| `POST /importacoes/plugin-autocad` (multipart `file` = DLL + `categoria` + lead do formulário do fabricante + `empresa?`, `host?`, `igsPorGrupo?`, `deflexao?`) | plugin que é casca de um catálogo web → baixa IGES/RFA da categoria para `catallog/<importId>/`, tessela, publica como biblioteca. O lead **nunca é persistido**. A DLL é inspecionada localmente (a rota HTTP de inspeção é dos conversores) |
| `GET /importacoes/:id` · `GET /importacoes?empresa=&limite=` | status `recebido → parseando → gravando → publicado \| vazio \| falhou`, `note` com progresso, `productCount`, `thumbCount`, `thumbFailed`, `diag`, links |
| `DELETE /importacoes/:id` | apaga importação terminada (produtos, `geo/`, `thumbs/`, documento); **409** em andamento |
| `POST /miniaturas/regerar {productId}` | **202**; regera a miniatura de um produto (chamado pelo editor após editar geometria) |
| `GET /exportar/catalogo/:id` | catálogo salvo → `.aq` novo (`catalogo_para_aq`), em stream; `X-Aq-Resumo` |
| `GET /health` | 200/503 pela conexão do Mongoose |

**Dentro:** `importacoes/` (entrada, fila em memória com `IMPORTACOES_CONCORRENCIA`, status, recuperação no boot —
órfãos viram `falhou` e uploads temporários somem), `publicacao/` (o caminho comum de tudo que vira catálogo:
upsert, `insertMany`, substituição do import anterior de mesmo slug; peça CAD), `miniaturas/` (por geometria, ainda
na vaga da fila; regeneração após edição em fila própria), `exportacao/`, `pipeline/` (a `Biblioteca` de `@bim/base`
como provider). Estados e limpeza em `docs/conhecimento/catalogo-modelo.md`.

Subir: `pnpm dev:criador` (raiz). Variáveis: `CRIADOR_PORT` (4100), `MONGODB_URI`, `MONGODB_DB`, `STORAGE_PATH`,
`IMPORTACOES_CONCORRENCIA`, `WEB_ORIGIN`, `BIBLIOTECA_DIR`, `PYTHON`. Para portar: este diretório + `pacotes/base` +
`pacotes/dominio` + `biblioteca/` (+ Chromium). Armadilha: `dev:criador` não tem watch — mudou TypeScript,
reinicie pelo pid de `ss -ltnp | grep ':4100 '`.
