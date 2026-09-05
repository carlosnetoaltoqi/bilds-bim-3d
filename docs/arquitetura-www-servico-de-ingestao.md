# Arquitetura — `www/` como serviço de ingestão + API de catálogo + web (2026-09-05)

> **Documento vivo.** Define a arquitetura-alvo do `www/` e o plano em etapas para chegar lá.
> Cada etapa concluída marca ✅ aqui e ganha um registro em `docs/sessoes/`. Enquanto o projeto
> viver neste repositório, é POC: **sem auth, sem admin** — a organização (empresa) existe como
> conceito, não como controle de acesso.

## 1. Decisões que definem a arquitetura

| # | Decisão | Por quê |
|---|---|---|
| A1 | **A ingestão é um serviço à parte** (`www/apps/ingestao`), desacoplado da API de leitura/edição (`www/apps/api`) e do web (`www/apps/web`). Falam entre si por HTTP e compartilham Mongo + storage. | Vai virar um deploy próprio consumido pela bilds.com. Aqui só abstraímos a fronteira, no mesmo sistema. |
| A2 | **O parse do `.aq` e a geração de catálogo, geometria e miniaturas usam o pipeline Python** (`read_aq.py`, `oq3d.py`, `dedup.py`, a lógica de `build_catalog_from_aq`) e as **miniaturas saem do Chromium via Playwright** (`thumbs.mjs` + `harness.html`). | É o caminho provado em produção (ZIP da bilds.com). O port TypeScript (`aq-reader.ts`, `oq3d-parser.ts`, `parse-worker.ts`, `thumb-rasterizer.ts`, `thumb-worker.ts`) **sai**: não se provou eficiente na geração de miniaturas. |
| A3 | O serviço é uma casca **NestJS fina** (upload, fila, status, recuperação no boot, gravação no Mongo) que roda o pipeline Python e o `thumbs.mjs` como **processos filhos**. | Reaproveita a infra endurecida em S7.11–S7.13 (fila, recuperação, validação, nome UTF-8) sem reescrever; o Python continua sendo o pipeline. |
| A4 | O código Python do pipeline **mora dentro do serviço** (`www/apps/ingestao/pipeline/`) e o pipeline estático (`scripts/build.py`) passa a importá-lo de lá. | O serviço tem de ser autocontido para ser isolado; o `build.py` vira consumidor da mesma biblioteca em vez de manter cópia. |
| A5 | Uma geometria por simbologia (como no pipeline), compartilhada entre produtos; **copy-on-write na primeira edição** (`PUT /geometrias/:id` de um produto que compartilha geometria grava um arquivo só dele). | Amanco: 856 produtos, 448 geometrias. Editar um produto não pode mudar os outros. |
| A6 | A miniatura é do produto (`thumbs/<importId>/<productId>.webp`) mas produtos que compartilham geometria compartilham o render: o serviço renderiza por geometria e grava a chave em cada produto. Regeneração após edição é pedida pela API ao serviço (`POST /miniaturas/regerar`). | Uma renderização por geometria; a API não tem Chromium nem Python. |
| A7 | **Sem auth**: login, JWT, `AuthGuard`, `SEED_USER`, middleware do Next e as rotas-proxy `/api/*` do web saem. O web fala direto com a API e com o serviço (CORS). | POC enquanto viver aqui. Empresa = agrupador de catálogos, escolhida por `customUrl` no import. |
| A8 | Todo catálogo publicado tem, na página pública, chamada para a edição (cabeçalho → `/editar`; modal do produto → `/editar/:produtoId`). Já existia; fica e é validado. | Pedido do usuário. |
| A9 | O gerador de `.aq` (`eng-reversa/`) **não é tocado** nesta fase. O editor continua exportando IFC (`ifc-export.ts`, no browser) e `.aq` (`geo_to_aq.py`, pelo serviço). | Escopo. |
| A10 | Filhos (Python e `thumbs.mjs`) **morrem quando o pai morre**: recebem `stdin` em pipe e saem ao ver EOF. | Substitui o `disconnect` do IPC (I29) sem `fork`. |

## 2. Topologia

```
www/
├── apps/
│   ├── ingestao/                 ← SERVIÇO DE INGESTÃO (Nest, :4100)  — futuro deploy próprio
│   │   ├── src/
│   │   │   ├── main.ts · app.module.ts · health/
│   │   │   ├── importacoes/      ← POST /importacoes (.aq|.zip|.stp|.step|.ifc), GET /importacoes/:id, GET /importacoes?empresa=
│   │   │   │   ├── importacoes.service.ts   (fila → pipeline → Mongo → miniaturas)
│   │   │   │   ├── recuperacao.service.ts   (boot: órfãos → falhou, tmp limpo)
│   │   │   │   └── fila.ts
│   │   │   ├── pipeline/         ← executa os processos filhos e lê o que produzem
│   │   │   │   ├── processo.ts              (spawn c/ timeout, ocioso, stdin-pipe, linhas de progresso)
│   │   │   │   ├── catalogo-aq.ts           (python3 pipeline/catalogo_de_aq.py → JSON do catálogo)
│   │   │   │   ├── cad.ts                   (step_to_geo.py | ifc_to_geo.py → {pos,col,idx})
│   │   │   │   └── miniaturas.ts            (node pipeline/thumbs.mjs → webp por geometria)
│   │   │   ├── cad/              ← POST /cad/tesselar (editor: adicionar parte), POST /exportar/aq
│   │   │   └── miniaturas/       ← POST /miniaturas/regerar {productId}
│   │   └── pipeline/             ← PYTHON + harness (autocontido; o build.py importa daqui)
│   │       ├── read_aq.py · oq3d.py · dedup.py · catalogo.py · inferencia.py
│   │       ├── catalogo_de_aq.py            (CLI: .aq → geo/<importId>/*.json + catálogo em JSON)
│   │       ├── step_to_geo.py · ifc_to_geo.py · parse_ifc.py · geo_to_aq.py
│   │       ├── thumbs.mjs · harness.html
│   │       └── requirements.txt
│   ├── api/                      ← API DE CATÁLOGO (Nest, :4000): leitura + edição
│   │   └── src/{catalogos,produtos,geometrias,thumbs,empresas,health}
│   └── web/                      ← Next (:3000): páginas públicas de catálogo + editor + importar
├── packages/
│   └── dominio/                  ← compartilhado: schemas Mongoose, storage-path, geometry-store, geo-buffers, asset-cache, validation, upload
└── storage/bim/{geo,thumbs,logos}   (gitignored)
```

### Contratos

**Serviço de ingestão** (`INGESTAO_URL`, padrão `http://localhost:4100`)

| Rota | O quê |
|---|---|
| `POST /importacoes` (multipart `file`, campos `empresa?`, `fabricante?`, `catalogo?`, `nome?`, `deflexao?`) | 202 `{importId, status:'recebido', statusUrl}`. Tipo pela extensão: `.aq`/`.zip` → biblioteca; `.stp`/`.step`/`.ifc` → peça CAD |
| `GET /importacoes/:importId` | `{status, note, error, productCount, catalogId, catalogoUrl?, editorUrl?, thumbCount…}` |
| `GET /importacoes?empresa=<customUrl>` | últimas importações da empresa |
| `POST /miniaturas/regerar` `{productId}` | 202; renderiza a miniatura do produto e grava `thumbKey`/`thumbAtualizadaEm`/`thumbErro` |
| `POST /cad/tesselar` (multipart) | síncrono: `{pos,col,idx,partes,…}` para "adicionar parte" no editor |
| `POST /exportar/aq` (JSON) | síncrono: download do `.aq` gerado pelo `geo_to_aq.py` |
| `GET /health` | 200/503 pela conexão do Mongoose |

Estados do import: `recebido → parseando → gravando → publicado | vazio | falhou`. `note` carrega a
posição na fila, o progresso do Python e o resumo das miniaturas.

**API de catálogo** (`API_URL`, padrão `http://localhost:4000`)

| Rota | O quê |
|---|---|
| `GET /empresas` · `POST /empresas` · `GET /empresas/:customUrl/catalogos` · `GET /logos/:companyId` | empresas e seus catálogos (sem auth) |
| `GET /catalogos/:empresa/:slug` · `PATCH /catalogos/:id` | página pública e edição dos metadados |
| `GET /produtos/:id` · `PATCH /produtos/:id` | informações do produto |
| `GET /geometrias/:id` · `GET …/original` · `PUT /geometrias/:id` · `POST …/restaurar` | geometria (ETag/304); PUT faz copy-on-write (A5) e pede a miniatura ao serviço (A6) |
| `GET /thumbs/:id` | miniatura (ETag/304) |

**Web** (`:3000`)

| Página | O quê |
|---|---|
| `/` | empresas e catálogos com links **ver** / **editar** / **importar** |
| `/empresa/criar` | cria empresa (nome, customUrl, logo) |
| `/importar` | sobe `.aq`/`.zip`/`.stp`/`.ifc` e acompanha o status (uma página para os dois tipos) |
| `/:empresa/:catalogo` | página pública (cards com miniatura, modal com 3D) — cabeçalho e modal com chamada para edição |
| `/:empresa/:catalogo/editar` · `/editar/:produtoId` | edição do catálogo e do produto (info + 3D + exportar IFC/.aq) |

### Fluxo de uma importação de `.aq`

```
web ──multipart──► ingestao POST /importacoes ──► BimImport{recebido} ──► Fila
  Fila ──► parseando: python3 pipeline/catalogo_de_aq.py <aq> --geo-dir <storage>/geo/<importId> --saida <tmp>.json
           (stderr = progresso → note)
        ──► gravando: upsert BimCatalog, insertMany BimProduct{geoKey: geo/<importId>/<geo>.json}
        ──► publicado
        ──► miniaturas (ainda na vaga da fila): node pipeline/thumbs.mjs cfg.json → thumbs/<importId>/<geo>.webp
            uma linha JSON por geometria → thumbKey em cada produto que usa a geometria; resumo em note/thumbCount
web ──GET /importacoes/:id (polling)──► "publicado" → link para /:empresa/:slug
```

## 3. Etapas

| Etapa | Entregável | Estado |
|---|---|---|
| **E0** | Este documento; inventário `docs/inventario-2026-09-05-fica-ou-sai.md`; sessão S7.14 | ✅ 2026-09-05 |
| **E1** | **Sai do `www/`** o que nada mais usa: spikes (`test-worker`, `test-port-s2-2`, `ingest-library`, `measure-thumbs`, `smoke-geometry-store`, `regen-thumbs`, `thumb-rasterizer-sw`), `workers/aq-parser` (Flask), os scripts deles no `package.json`, e **toda a auth** (login, JWT, `AuthGuard`, `SEED_*`, middleware do Next, rotas-proxy `/api/*` do web). Empresas ganham `GET /empresas`, `GET /empresas/:customUrl[/catalogos]`; o import de `.aq` recebe `empresa` (customUrl). `/empresa` vira a lista de empresas e catálogos com ver/editar/importar. O port TS fica até a E3 (o import continua funcionando enquanto o serviço não existe). | ✅ 2026-09-05 (S7.14) |
| **E2** | **Pipeline Python dentro do serviço:** `www/apps/ingestao/pipeline/` com `read_aq`, `oq3d`, `dedup`, `catalogo` (extraído de `build.py`), `inferencia`, `catalogo_de_aq.py` (CLI), conversores CAD, `thumbs.mjs`+`harness.html` (servindo `/vendor` de qualquer `three`); `scripts/build.py` importa daqui; `tests/` verdes. | ⬜ |
| **E3** | **Serviço `apps/ingestao`** (Nest): importações `.aq`/`.zip`/CAD pela fila, worker Python, miniaturas por `thumbs.mjs`, recuperação no boot, `POST /miniaturas/regerar`, `cad/tesselar`, `exportar/aq`; `packages/dominio`; API sem `importacoes`/`step`, com copy-on-write e cliente do serviço. | ⬜ |
| **E4** | **Web sem login:** `/` (empresas + catálogos), `/importar` unificada, `/empresa/criar`; páginas de catálogo com a chamada para edição validada; editor apontando para os dois serviços. | ⬜ |
| **E5** | **Testes e CI:** harnesses para `processo.ts`, fila, recuperação, DTOs, copy-on-write; `ci.yml` com os três apps; teste de aceitação com Mongo + Chromium (import Dancor → página → editar → miniatura regerada). | ⬜ |
| **E6** | **Documentação final:** `www/README.md` reescrito (subir os três, contratos, `.env`), `docs/conhecimento/diagnostico.md`, `CLAUDE.md` (mapa), `README.md` da raiz. | ⬜ |

Regras de execução: um commit por item; cada etapa termina com `pnpm -r build` verde em `www/` e
`python3 -m pytest -m "not thumbs"` verde; documentação atualizada no mesmo commit da etapa.

## 4. O que fica fora (por enquanto)

- `eng-reversa/` (gerador de `.aq` a partir de PDF) — A9.
- Auth/admin/visibilidade de catálogo — quando sair deste repositório.
- Storage fora do disco (S3) — `IGeometryStore` já é o ponto de troca.
- Fila fora do processo — a `Fila` em memória + recuperação no boot bastam para uma instância.
