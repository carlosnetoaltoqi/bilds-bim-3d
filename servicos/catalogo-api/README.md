# servicos/catalogo-api — leitura de catálogo (:4000)

A **API de catálogo** (docs/arquitetura.md §2): o que a página pública e o editor leem — empresas, catálogos,
produtos, geometria e miniaturas (com ETag/304) — e a remoção em cascata em cada nível. Sem Python, sem
Chromium, não fala com nenhum outro serviço. Escrever é dos outros contextos: publicar é do criador, editar
peça é do editor; aqui só `PATCH` dos metadados do catálogo e `POST /empresas`.

| Rota | O quê |
|---|---|
| `GET /empresas` · `POST /empresas` · `GET /empresas/:customUrl[/catalogos]` · `GET /logos/:companyId` · `DELETE /empresas/:customUrl` | empresas (agrupador de catálogos, sem auth — ADR-007) |
| `GET /catalogos/:empresa/:slug` · `PATCH /catalogos/:id` (title, manufacturer, layout) · `DELETE /catalogos/:id` | página pública; metadados; apagar com produtos, storage e imports |
| `GET /produtos/:id` · `DELETE /produtos/:id` | produto (com `infoOriginal`, `thumbAtualizadaEm`, `thumbErro`); apagar (geometria/miniatura só com o último usuário) |
| `GET /geometrias/:id` · `GET /thumbs/:id` | `{pos,col,idx}` e WebP, com ETag/304 |
| `GET /health` | 200/503 pela conexão do Mongoose |

Subir: `pnpm dev:catalogo` (raiz). Variáveis: `CATALOGO_PORT` (4000), `MONGODB_URI`, `MONGODB_DB`, `STORAGE_PATH`,
`WEB_ORIGIN`. Para portar: este diretório + `pacotes/base` + `pacotes/dominio` + `web/src/components/bim-catalog`.

**Mongo Atlas e o whitelist de IP:** quando o IP da máquina muda, o Mongoose entra em retry e culpa o whitelist
para qualquer causa (DNS, rede, cluster pausado, credencial). A assinatura real do IP não liberado é o TCP
`:27017` abrir e o TLS morrer com `SSL alert number 80` nos três nós. Libere em Network Access → Add Current IP
(`curl -s https://api.ipify.org`); o serviço reconecta sozinho. Um Mongo local tira o whitelist do caminho.
