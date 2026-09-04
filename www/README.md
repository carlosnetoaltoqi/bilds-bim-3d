# www — POC dinâmica + POC de edição

Monorepo pnpm com a API NestJS (`apps/api`, porta 4000) e o web Next.js (`apps/web`,
porta 3000). A **fonte de verdade** sobre arquitetura, decisões e armadilhas é o
`CLAUDE.md` da raiz — este arquivo é só o mapa para começar.

## Subir

```bash
cp .env.example .env            # e preencher (Mongo, seed, JWT, STORAGE_PATH)
pnpm install
pnpm dev:api                    # http://localhost:4000
pnpm dev:web                    # http://localhost:3000  (outro terminal)
```

Conversores CAD (só para importar STEP/IFC e exportar `.aq`; o resto não precisa):

```bash
pip install --user --break-system-packages cadquery-ocp ifcopenshell
```

Se a API ficar em `Retrying (n)...` com o Mongoose culpando o whitelist, é o IP no Atlas —
ver `CLAUDE.md`, "A API não sobe e o Mongoose culpa o whitelist".

## Rotas

| Rota | Auth | O quê |
|---|---|---|
| `POST /auth/login` | — | JWT do usuário semente (não consulta o banco) |
| `POST /empresas`, `GET /empresas/minha`, `GET /logos/:id` | Bearer | empresa do usuário |
| `POST /importacoes`, `GET /importacoes/ultima`, `GET /importacoes/:id` | Bearer | import de `.aq` (worker em processo filho) |
| `GET /catalogos/:empresa/:slug` | — | catálogo público `{ catalog, products }` |
| `PATCH /catalogos/:catalogId` | — | título, fabricante, layout (POC de edição) |
| `GET /produtos/:id`, `PATCH /produtos/:id` | — | informações do produto; `infoOriginal` na 1ª edição |
| `GET /geometrias/:id` | — | `{pos,col,idx}` com ETag por tamanho+mtime |
| `PUT /geometrias/:id`, `GET …/original`, `POST …/restaurar` | — | geometria editada; original preservado em `<id>.orig.json` |
| `GET /thumbs/:id` | — | miniatura WebP |
| `POST /cad/importar` (`?sync=1`), `GET /cad/importacoes/:id` | — | STEP/IFC → produto, assíncrono com status |
| `POST /cad/tesselar` | — | STEP/IFC → geometria, para "adicionar parte" no editor |
| `POST /exportar/aq` | — | partes do editor → `.aq` (download) |
| `GET /health` | — | `{ status, mongo }` |

`/step/importar` e `/step/tesselar` são aliases de `/cad/*`.

Páginas do web: `/login`, `/empresa`, `/empresa/criar`, `/empresa/importar` (com login);
`/:empresa/:catalogo` (pública), `/:empresa/:catalogo/editar[/:produtoId]` e `/importar-step`
(sem login — POC de edição).

## Testes

```bash
bash tools/testes-editor.sh                                   # round-trips sem browser (Node + Python)
ROUNDTRIP_SABOTAR=1 bash tools/testes-editor.sh               # tem de falhar — autoteste da métrica do round-trip
node tools/e2e/e2e-editor.mjs --validar                       # editor no browser (Playwright + SwiftShader)
node tools/e2e/e2e-cad-import.mjs ../input/STEP/2831A09.stp   # importar CAD e abrir no editor
pnpm smoke:geo · pnpm thumb:measure · pnpm thumb:regen        # ferramentas da POC dinâmica (tools/)
```

O Playwright vem do `pnpm install` da **raiz** do repositório (o mesmo do `scripts/thumbs.mjs`).

## Onde está o quê

| Pasta | Conteúdo |
|---|---|
| `apps/api/src/{importacoes,catalogos,geometrias,produtos,step,thumbs,empresas,auth}` | um módulo Nest por assunto; `common/` tem o validador `{pos,col,idx}` e o ETag |
| `apps/api/src/geometry-store/` | `IGeometryStore` + `DiskGeometryStore` (ponto de troca para S3) |
| `apps/web/src/components/bim-catalog/` | viewer público: cards, modal, `bim-viewer-engine.ts` (buildScene) |
| `apps/web/src/components/bim-editor/` | editor: `mesh-model.ts` (puro), `EditorViewport.tsx`, `GeometryPanel.tsx`, `InfoForm.tsx`, `ifc-export.ts`, `ProductEditor.tsx` |
| `tools/` | port TS do leitor `.aq`/OQ3D, rasterizador de thumbs, scripts de medição e os testes |
| `storage/bim/` | `geo/`, `thumbs/`, `logos/` — gitignored, regenerável por import |
| `../scripts/{step_to_geo,ifc_to_geo,geo_to_aq}.py` | conversores CAD chamados pela API |
