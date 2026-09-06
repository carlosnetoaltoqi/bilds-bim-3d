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
| A9 | O gerador de catálogo da Akato (`eng-reversa/`) não é tocado. O editor continua exportando IFC (`ifc-export.ts`, no browser) e `.aq` (`geo_to_aq.py`, pelo serviço). **Adendo (I4, S7.15):** a parte genérica do escritor de `.aq` (`aq_writer.py`, `oq3d_writer.py`, `schema-aq-607.sql`) foi promovida para o pipeline; o `gerar_aq.py` da Akato herda dela. | Escopo; o serviço tem de ser autocontido. |
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
| `POST /importacoes` (multipart `file`, campos `empresa?`, `fabricante?`, `catalogo?`, `nome?`, `deflexao?`) | 202 `{importId, status:'recebido', statusUrl}`. Tipo pela extensão: `.aq`/`.zip` → biblioteca; `.stp`/`.step`/`.igs`/`.ifc` → peça CAD |
| `POST /importacoes/plugin-autocad/inspecionar` (multipart DLL) · `POST /importacoes/plugin-autocad` (DLL + `categoria` + lead + `empresa?`, `host?`, `igsPorGrupo?`, `deflexao?`) | S7.17: plugin de AutoCAD da plataforma Catallog → catálogo web → IGES/RFA da categoria → catálogo (tipo `plugin`, mesmo caminho de publicação da biblioteca); downloads em `catallog/<importId>/` |
| `GET /importacoes/:importId` | `{status, note, error, productCount, catalogId, catalogoUrl?, editorUrl?, thumbCount…}` |
| `GET /importacoes?empresa=<customUrl>` | últimas importações da empresa |
| `DELETE /importacoes/:importId` | apaga importação terminada (produtos, storage, documento; 409 em andamento) |
| `POST /miniaturas/regerar` `{productId}` | 202; renderiza a miniatura do produto e grava `thumbKey`/`thumbAtualizadaEm`/`thumbErro` |
| `POST /cad/tesselar` (multipart) | síncrono: `{pos,col,idx,partes,…}` — usado pela página `/cad` do web |
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
| `DELETE /empresas/:customUrl` · `DELETE /catalogos/:id` · `DELETE /produtos/:id` | apagar em cascata (`dominio/remocao.ts`); geometria/miniatura compartilhadas só saem com o último produto |

**Web** (`:3000`)

| Página | O quê |
|---|---|
| `/` | empresas e catálogos com links **ver** / **editar** / **importar**; menu **Importar biblioteca .aq** · **Importar peça STEP / IGES / IFC** · **Importar plugin do AutoCAD** · **Converter peça CAD** · **Criar empresa** |
| `/importar/plugin` | DLL do plugin → inspecionar → categoria + formulário do fabricante → import tipo `plugin` (S7.17) |
| `/empresa/criar` | cria empresa (nome, customUrl, logo) |
| `/importar[?tipo=aq\|cad]` | sobe `.aq`/`.zip`/`.stp`/`.ifc` e acompanha o status (uma página para os dois tipos; `tipo` restringe) |
| `/cad` | converter STEP/IFC sem criar produto (viewer + download JSON/IFC/.aq) |
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
| **E2** | **Pipeline Python dentro do serviço:** `www/apps/ingestao/pipeline/` com `read_aq`, `oq3d`, `dedup`, `catalogo` (extraído de `build.py`), `inferencia`, `miniaturas`, `processo` (vigia do stdin), `catalogo_de_aq.py` (CLI, contrato na docstring), conversores CAD, `thumbs.mjs`+`harness.html` (montagens `/harness.html`, `/vendor`, `/geo` — serve o `three` de qualquer lugar); `scripts/build.py` de 1.290 → 695 linhas, importa daqui; `tests/` 106 verdes; CLI validada na Dancor (13 produtos, 13 miniaturas, 9,7 s). | ✅ 2026-09-05 (S7.14) |
| **E3** | **Serviço `apps/ingestao`** (Nest, :4100): `POST /importacoes` (`.aq`/`.zip`/`.stp`/`.ifc`, fila), `PipelineService` roda `catalogo_de_aq.py`/`step_to_geo.py`/`ifc_to_geo.py`/`geo_to_aq.py`/`thumbs.mjs` via `processo.ts` (timeout, ociosidade, stdin em pipe), recuperação no boot, `POST /miniaturas/regerar` (fila própria), `cad/tesselar`, `exportar/aq`; `packages/dominio` (`@bim/dominio`: schemas, storage, validação, ETag, upload); API sem `importacoes`/`step`/port TS, `PUT /geometrias` com copy-on-write (A5) e `IngestaoClient` (A6); `test_paridade_ts`/`test_worker_ipc` saem, entram `test_processo` e os cenários de copy-on-write; suíte **102** testes. **Pendência:** `tsc` não emite o `@bim/dominio` no `dist/` (o symlink do workspace é tratado como externo) — `pnpm start` do `dist/` não roda; o modo dev (`ts-node`) é o único que funciona até o build do deploy ser feito. | ✅ 2026-09-05 (S7.14) |
| **E4** | **Web sem login:** `/` (empresas + catálogos), `/importar` unificada, `/empresa/criar`; páginas de catálogo com a chamada para edição validada; editor apontando para os dois serviços. | ⬜ |
| **E5** | **Testes e aceitação:** `test_processo` (executar: saída, sinal, timeout, ocioso, spawn, stdin aberto; `vigiar_stdin`; `thumbs.mjs` para no EOF), `geometrias_thumb` (exclusiva, copy-on-write, serviço fora, DTO), `test_www_config`/`test_www_deps` para três importers; `ci.yml` compila os três apps. **Teste de aceitação com os três serviços + Atlas + Chromium** (registro em `docs/sessoes/S7.14-…`): Dancor 13/13 em 11 s; **Amanco 856 produtos, 448 geometrias, 448 miniaturas em 58 s**; páginas `/`, `/importar`, catálogo (com "editar catálogo"), `/editar`; PUT → miniatura regerada pelo serviço → restaurar; copy-on-write real em `joelho-45-duplo-50mm` (o irmão intacto, miniaturas distintas, restaurar desfaz); `kill -9` no serviço com o Python a 100 geometrias → filho saiu sozinho, boot marcou `falhou` e limpou `geo/`. Achou e corrigiu: `three/build/three.module.js` fora do `exports` (miniaturas falhavam) e `deleteByPrefix` deixando o diretório. | ✅ 2026-09-05 (S7.14) |
| **E6** | **Documentação:** `www/README.md` reescrito (três apps, contratos, fluxo, estado da base, decisões/pendências, `.env`, Atlas), `docs/conhecimento/diagnostico.md` (+8 linhas), `CLAUDE.md` (mapa, testes, fase atual), `README.md` da raiz, `pipeline/README.md`, sessão S7.14. | ✅ 2026-09-05 (S7.14) |

Regras de execução: um commit por item; cada etapa termina com `pnpm -r build` verde em `www/` e
`python3 -m pytest -m "not thumbs"` verde; documentação atualizada no mesmo commit da etapa.

## 4. Pendências deixadas pela S7.14

- **Build para deploy**: o `tsc` não emite `@bim/dominio` no `dist/` (symlink do workspace é externo) — `pnpm start` não roda; só `pnpm dev:*`. Resolver ao isolar o serviço (compilar o dominio com `main` para `dist`, ou bundler).
- `tools/e2e/e2e-editor.mjs` e `e2e-cad-import.mjs` apontam para os serviços novos mas não foram reexecutados.
- Teste automatizado de aceitação (subir serviço + API com Mongo local, importar Dancor, editar) — hoje é roteiro manual na sessão.
- `GET /importacoes` faz três consultas por item; `www/README.md` "Estado da base" precisa ser atualizado a cada carga.
- ~~I32~~ (fechado na S7.15: `MongoProntoGuard` → 503 na hora), Nest 11 (multer novo), `IngestaoClient` com timeout de 10 s no `PUT` (se o serviço travar, o PUT demora 10 s).
- ~~C7~~ fechado na S7.15: preview só local, `vercel.json` removido. ~~I4~~ fechado na S7.15: pipeline autocontido.
- `eng-reversa/tools/validar_aq.py` quebra no passo 4 (`import build` — `scripts/` não está no `sys.path` dele desde a E2); visto na S7.16 ao validar o `.aq` exportado. `eng-reversa/` está intocado por decisão do usuário — corrigir quando ele decidir mexer lá.
- O inventário `docs/inventario-2026-09-05-fica-ou-sai.md` foi escrito ANTES desta arquitetura: as decisões D1–D3 dele foram superadas pela direção do usuário (o repo limpo é o `www/` de três apps + pipeline); o resto (arquivo/sai) continua válido.

## 5. O que fica fora (por enquanto)

- `eng-reversa/` (gerador de `.aq` a partir de PDF) — A9.
- Auth/admin/visibilidade de catálogo — quando sair deste repositório.
- Storage fora do disco (S3) — `IGeometryStore` já é o ponto de troca.
- Fila fora do processo — a `Fila` em memória + recuperação no boot bastam para uma instância.
