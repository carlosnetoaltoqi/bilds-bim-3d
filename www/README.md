# www — POC dinâmica + POC de edição

Monorepo pnpm com a API NestJS (`apps/api`, porta 4000) e o web Next.js (`apps/web`,
porta 3000). Este arquivo é a **fonte de verdade da POC**: o mapa para subir e, mais abaixo,
estado da base, decisões e armadilhas (movidos do `CLAUDE.md` em 2026-09-04, I22). O
`CLAUDE.md` da raiz só aponta para cá.

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
ver "A API não sobe e o Mongoose culpa o whitelist", abaixo.

## Rotas

| Rota | Auth | O quê |
|---|---|---|
| `POST /auth/login` | — | JWT do usuário semente (não consulta o banco) |
| `POST /empresas`, `GET /empresas/minha`, `GET /logos/:id` | Bearer | empresa do usuário |
| `POST /importacoes`, `GET /importacoes/ultima`, `GET /importacoes/:id` | Bearer | import de `.aq` (worker em processo filho); o documento traz `thumbCount`/`thumbFailed`/`thumbError` e o `note` ganha `miniaturas: N/M geradas…` ao fim do lote (I15); uma importação por vez, as outras esperam em `recebido` com `na fila — N à frente` (I11) |
| `GET /catalogos/:empresa/:slug` | — | catálogo público `{ catalog, products }` |
| `PATCH /catalogos/:catalogId` | — | título, fabricante, layout (POC de edição); corpo validado por `PatchCatalogoDto` (I16) |
| `GET /produtos/:id`, `PATCH /produtos/:id` | — | informações do produto; `infoOriginal` na 1ª edição; corpo validado por `PatchProdutoDto` — campo fora do DTO é 400, `specs` só texto/número/booleano, `curva` ≤ 1000 pontos (I16) |
| `GET /geometrias/:id` | — | `{pos,col,idx}` com ETag por tamanho+mtime |
| `PUT /geometrias/:id`, `GET …/original`, `POST …/restaurar` | — | geometria editada; original preservado em `<id>.orig.json`; ambos regeram a miniatura em segundo plano (I14) — `thumbAtualizadaEm`/`thumbErro` no produto |
| `GET /thumbs/:id` | — | miniatura WebP |
| `POST /cad/importar` (`?sync=1`), `GET /cad/importacoes/:id` | — | STEP/IFC → produto, assíncrono com status; campos do formulário em `ImportarCadDto` (`deflexao` 0 < mm ≤ 10); mesma fila dos `.aq` (I11) |
| `POST /cad/tesselar` | — | STEP/IFC → geometria, para "adicionar parte" no editor |
| `POST /exportar/aq` | — | partes do editor → `.aq` (download) |
| `GET /health` | — | `{ status, mongo, conexao, banco }` pela conexão do Mongoose da API; **503** com o `readyState` quando desconectada (I12) |

`/step/importar` e `/step/tesselar` são aliases de `/cad/*`.

Páginas do web: `/login`, `/empresa`, `/empresa/criar`, `/empresa/importar` (com login);
`/:empresa/:catalogo` (pública), `/:empresa/:catalogo/editar[/:produtoId]` e `/importar-step`
(sem login — POC de edição).

## Testes

```bash
bash tools/testes-editor.sh                                   # round-trips sem browser (Node + Python)
ROUNDTRIP_SABOTAR=1 bash tools/testes-editor.sh               # tem de falhar — autoteste da métrica do mesh-model
ROUNDTRIP_SABOTAR_IFC=1 bash tools/testes-editor.sh           # tem de falhar — autoteste da conferência do IFC exportado
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

---

## Estado da base e do storage — única versão válida (2026-09-03)

> Movido do `CLAUDE.md` em 2026-09-04 (S7.8, item I22 da auditoria). O conteúdo é o que estava lá,
> com as afirmações desatualizadas de I23 corrigidas no lugar; onde diz "este arquivo", "acima" ou
> "no histórico", leia-se o `CLAUDE.md` antigo — o histórico está em `docs/sessoes/`. **Manter aqui**
> a partir de agora: o `CLAUDE.md` só aponta para este arquivo; a tabela abaixo substitui as três versões contraditórias que havia (C10).

**A POC de catálogo dinâmico está encerrada** (2026-08-31). Em 2026-09-02 banco e storage
foram esvaziados de propósito. **Em 2026-09-03 a POC de edição recarregou a Dancor**
para servir de base à POC de edição (ver "POC de edição", abaixo):

| O quê | Estado atual |
|---|---|
| `companies` | **1** — `poc-edicao` (customUrl), sem logo |
| `bim_catalogs` | **3** — `bomba-de-combate-a-incencio` (13 produtos, `series-rows`), `pecas-step` (1, de `input/STEP/2831A09.stp`) e `pecas-ifc` (4: a 2CV editada reimportada do IFC ×2, a peça STEP via IFC, e o `Projeto4.ifc` do Revit com 760 mil triângulos) |
| `bim_imports` | **6** — Dancor, STEP e quatro IFC, todos `publicado` |
| `bim_products` | **18**, todos com `geoKey` e `thumbKey` |
| `www/storage/bim/geo/<importId>/` | um diretório por import; o do Projeto4 tem um JSON de 31 MB (o `.orig.json` só aparece depois de editar geometria) |
| Editor | `http://localhost:3000/poc-edicao/<slug>/editar` para os três catálogos |
| Importar STEP ou IFC | `http://localhost:3000/importar-step` (STEP precisa do `OCP` em Python — ver abaixo) |

Para voltar ao vazio: `deleteMany({})` nas quatro coleções e apagar `www/storage/bim/*/*`
(receita em `docs/sessoes/2026-09-02-poc-subida-local-armadilha-do-atlas-e-limpeza-da-base.md`).

O que a API devolve com a base **vazia**, conferido em 2026-09-02:

| Requisição | Resposta |
|---|---|
| `GET /catalogos/:empresa/:slug` | `404` |
| `GET /empresas/minha` | `404 empresa não encontrada` |
| `GET /importacoes/ultima` | `200` com corpo vazio |
| `POST /auth/login` | `200` com token — **não consulta o banco** (ADR 7.6) |
| `GET /{empresa}/{catalogo}` no web | `404` |
| `/empresa` sem sessão | `307` para `/login` |

> **Recarregar é só importar de novo.** `input/` tem **16** `.aq` nesta máquina (Akato ×2, Amanco,
> Dancor, Intelbras ×7, Komeco ×4, Maxbar); `input/` é gitignored. As chaves em disco embutem o `importId`,
> então o que foi apagado não se reconstitui; **re-importar** produz um `importId` novo.
> Sem interface, pela API:
>
> ```bash
> cd www && set -a && . ./.env && set +a
> TOKEN=$(curl -s -X POST localhost:4000/auth/login -H 'content-type: application/json' \
>   -d "{\"email\":\"$SEED_USER\",\"password\":\"$SEED_PASSWORD\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
> curl -s -X POST localhost:4000/empresas -H "Authorization: Bearer $TOKEN" -F name="POC" -F customUrl=poc
> curl -s -X POST localhost:4000/importacoes -H "Authorization: Bearer $TOKEN" -F "file=@../input/Dancor/pecas_dancor_bombas_incendio_2026_04.1.aq"
> ```

### O que havia antes, e como foi validado (histórico)

A carga que existia até 2026-09-02 foi a da S5.2 — as duas bibliotecas reimportadas do
zero pela interface depois da correção do `oq3d.py` (S5.1). Ela **passou** em tudo o que
se pediu dela, e é a prova de que o caminho funciona ponta a ponta. Reconferido em
2026-09-02, antes de apagar:

| O quê | Estado então |
|---|---|
| Empresa | 1 em `companies` |
| Catálogo Dancor | `bomba-de-combate-a-incencio` — 13 produtos, `series-rows` |
| Catálogo Amanco | `pvc-esgoto-silentium` — 856 produtos, `catalog-grid` |
| Produtos | **869 — todos com `geoKey` e `thumbKey`** (servidos pela API como `geoUrl`/`thumbUrl`) |
| Storage | 364 MB, 1.738 arquivos em `www/storage/bim` |
| Geometria | CAM-W21 2CV com **27.425 triângulos** = parser corrigido (seria 20.452 com o antigo) |
| Miniaturas | `200 image/webp`, imagem distinta por produto |
| Revalidação de cache (S6.1) | 1ª visita `200`, condicional com ETag `304` |
| Páginas públicas | ambas `200` no web (3000) e na API (4000) |

Registro da validação original em `docs/sessoes/S5.2-encerramento-poc.md`.

> **A resposta de `GET /catalogos/:empresa/:slug` tem raiz `{ catalog, products }`** — em
> inglês, e não `produtos` como o `catalog.json` do pipeline estático. Os campos do produto
> são `geoUrl`/`thumbUrl` (URLs relativas, que o Server Component converte em absolutas), e
> não `geoKey`/`thumbKey` — esses são os nomes no documento do Mongo. Vale saber antes de
> escrever qualquer cliente novo.

**Versão base estável:** o topo de `main` (desde 2026-09-04 a `poc-edicao` está mergeada). Confira com `git log --oneline -1`.

### Quatro linhas de trabalho

1. **Pipeline estático (esta é a linha madura).** `.aq` → catálogo → ZIP/preview → Vercel.
   É o que o `CLAUDE.md` e `docs/conhecimento/pipeline-estatico.md` documentam. Estável e em produção.
2. **Engenharia reversa da escrita de `.aq`** (`eng-reversa/`, 2026-09-02) — ver o histórico.
3. **POC de edição** (`www/`, 2026-09-03) — editar informações e modelo 3D
   sobre a POC dinâmica. Ver "POC de edição", abaixo.
4. **POC de catálogo dinâmico** — **ENCERRADA em 2026-08-31.** As 14 sessões
   (S-rev a S4.3) mais a correção do parser (S5.1) e a validação final (S5.2) foram
   executadas. Aprendizados destilados em
   `docs/solutions/architecture-patterns/poc-catalogo-bim-dinamico-aprendizados.md`.
   O documento registra as respostas às cinco perguntas da POC, os bugs encontrados e
   as diretrizes para a reconstrução na bilds.com.

   O estado atual do banco e do storage é o da tabela no topo desta seção — **a única
   versão que vale** (C10). A carga da POC dinâmica foi apagada em 2026-09-02 e a Dancor
   reimportada em 2026-09-03 para a POC de edição; os 16 `.aq` estão em `input/`.

   **Miniaturas (S4.4, 2026-08-30) — resolvidas.** O rasterizador software foi substituído
   por Playwright + `templates/thumbs/harness.html` no `thumb-worker.ts`: a miniatura sai do
   **mesmo Three.js, mesmo `buildScene()` e mesma câmera** do viewer. Medido, contra o render
   do viewer: **47 dB de PSNR** (o piso da compressão WebP q=0,85) contra **27 dB** do
   rasterizador software. 13 produtos Dancor em **~6,3 s**. Ver
   `docs/solutions/architecture-patterns/thumb-qualidade-identica-ao-viewer.md` e
   `docs/sessoes/S4.4-thumbs-playwright.md`.

   Números de medição de S4.1 (para referência):
   - HTML inicial: 71.9 KB (SSR) vs 44 KB (estático) — 1.6× maior
   - 13 thumbs: 57 KB total (≈ igual nos dois modelos)
   - TTFB SSR: 177–254ms vs ~2ms local (CDN ~50ms)
   - LCP estimado: ~300ms (POC) vs ~100ms (CDN com thumbs) — 3× mais lento
   - Registro completo: `docs/sessoes/S4.1-medicao-comparativa.md`

   **Não há próxima sessão desta linha.** Quem for iniciar a reconstrução na bilds.com
   deve ler `docs/solutions/architecture-patterns/poc-catalogo-bim-dinamico-aprendizados.md`
   e `docs/plano-produto-dinamico.md` (seção 13 — o que a POC não implementa).

### POC de edição (2026-09-03)

Sobre a POC dinâmica (`www/`), sem mexer no import nem no viewer público: **editar as
informações do produto no Mongo e o modelo 3D na tela, gravando de volta o JSON que o
viewer lê.** Sem autenticação (rotas novas sem guard; páginas fora do matcher do
middleware). Roda local. Registro completo em `docs/sessoes/S7.1-poc-edicao.md`.

| Camada | O quê |
|---|---|
| API | `PUT /geometrias/:id` (valida `{pos,col,idx}`, grava via GeometryStore preservando o original em `<id>.orig.json` e dispara `regerarMiniatura` — I14), `GET /geometrias/:id/original`, `POST /geometrias/:id/restaurar` (idem), `GET|PATCH /produtos/:id`, `PATCH /catalogos/:id`. Body JSON até 300 MB (`JSON_BODY_LIMIT`). |
| Web | `/:empresa/:catalogo/editar` (lista + catálogo) e `/:empresa/:catalogo/editar/:produtoId` (editor). Links "editar" no modal e no hero. |
| Modelo | `www/apps/web/src/components/bim-editor/mesh-model.ts` — puro, sem React. |

**A ideia central: re-segmentar o JSON plano em partes.** O storage guarda `{pos,col,idx}`
sem hierarquia; o editor divide a malha em **componentes conexos do grafo de triângulos**.
Funciona porque o dedup do import põe a cor na chave — dois triângulos de cores diferentes
nunca compartilham vértice — logo cada componente sai com cor uniforme e o conjunto
aproxima as `TQi3DTriangleMesh` originais (58 partes na 20CV da Dancor, 31 na 2CV). Os
bocais do AltoQi (verde `1,154,63`, azuis `10,84,152` e `0,116,232`) são detectados pela
cor e listados como "Bocal N".

Cada parte é `{pos, col, idx, matrix 4×4, visible, marker}`. Editar é mexer na matriz
(TransformControls ou campos numéricos em cm/graus), na cor, na visibilidade, espelhar,
inverter normais, fundir, duplicar, excluir, adicionar primitiva (caixa, cilindro, tubo)
ou malha externa (STL/OBJ/JSON com unidade). Operações globais: centrar, apoiar em y=0,
girar 90°, escala ×0,01…×100, remover bocais, re-segmentar. Undo/redo por snapshot
(partes imutáveis — um snapshot custa o array de referências).

**Salvar = `bake()`:** aplica as matrizes das partes visíveis, concatena, arredonda a
1 µm e deduplica com **o mesmo algoritmo float32 do `parse-worker.ts`**. Round-trip sem
edição preserva todos os triângulos (68.488 = 68.488) e reduz o JSON pela metade
(6,3 MB → 3,2 MB) porque o arredondamento funde vizinhos a menos de 1 µm que o float32
distinguia (239 vértices em 44.242 na 20CV). Partes ocultas **não** entram no arquivo.

**Diagnóstico de malha no painel:** vértices, triângulos, arestas de borda (um só
triângulo), não-manifold (>2), degenerados, bbox em cm. **Atenção à leitura das arestas
de borda:** nas 13 geometrias da Dancor **25–32% das arestas são de borda** — a
tesselação do fabricante chega como sopa de triângulos e o dedup exato não solda as
emendas. O número só é alarme em malha **gerada ou importada**, que deve dar 0 (o tubo
paramétrico dá 0; o perfil não soldado do `eng-reversa` daria `2 × lados`).

Viewport: mesma luz, fundo e material do `buildScene()` do viewer, para o que se vê ser
o que o visitante verá. Plano de corte em Y (corta também o fantasma laranja do original,
senão a comparação não faz sentido), grade em cm proporcional ao modelo, eixos na origem.
Atalhos: 1–4 ferramentas, F enquadra, H oculta, Del exclui, Ctrl+Z/Shift+Z, Ctrl+S.

**Exportar IFC4** (`ifc-export.ts`, botões "Exportar IFC" e "salvar geometria e exportar
IFC"): gera o STEP **do que está na tela**, salvo ou não, separado do storage. É o inverso
do `parse_ifc.py` e obedece às armadilhas dele: uma entidade por linha; a
`IFCELEMENTASSEMBLY` (o produto) **sem** Representation e uma `IFCBUILDINGELEMENTPROXY`
por parte (o parser processa os dois tipos — geometria nos dois contaria em dobro);
`METRE` com valores em metros (o parser não converte unidade); eixos `ifc = (x, −z, y)`;
`REAL` sempre com ponto e sem expoente; `IFCINDEXEDCOLOURMAP` com índice 1-based por
triângulo mais `IFCSTYLEDITEM` para viewers que ignoram o mapa; `Closed=.T.` só sem
aresta de borda. Matriz rígida (ortonormal, det>0) vira `IFCLOCALPLACEMENT` com
`Axis = C·coluna_Y`, `RefDirection = C·coluna_X`; escala é assada nos vértices. As
informações do Mongo viajam em `IFCPROPERTYSET` (`bilds_Produto`, `bilds_Especificacoes`),
com acento em `\X2\…\X0\`. Verificado na 2CV com uma parte girada+deslocada, uma
escalada e um tubo novo: `parse_ifc.py` devolve os **mesmos 27.937 triângulos**, todo vértice
com par a ≤ 2 µm nos dois sentidos (desvio máximo **1,26 µm** — o "14 µm" que constava aqui até
2026-09-05 era artefato da comparação por buckets a 10 µm, I26), `ifcopenshell.validate`
**0 erros**, psets lidos de volta com "Incêndio" íntegro. O
`ifcopenshell.geom` conta 27.871 (descarta 66 degenerados — também conhecido).

**STEP → editor, e editor → `.aq`** (S7.2, `docs/sessoes/S7.2-step-e-aq.md`). Um `.stp`
é ISO 10303-21 como o IFC, mas B-rep paramétrico: não há triângulo no arquivo, a malha
nasce na tesselação. `scripts/step_to_geo.py` faz isso com OpenCASCADE (`pip install --user
--break-system-packages cadquery-ocp`, 165 MB em `~/.local`): nomes e cores via XCAF, cor
por face, sentido invertido nas faces `REVERSED`, `×0,001` (o OCC entrega mm) e `(x, z, −y)`,
dedup do pipeline. `POST /step/importar` (e a página `/importar-step`) tessela e cria um
produto no catálogo `pecas-step` — daí o editor abre a peça como qualquer outra;
`POST /step/tesselar` acrescenta um STEP como partes de um produto existente. No sentido
inverso, `scripts/geo_to_aq.py` embala as partes do editor num `.aq` mínimo — schema 607,
`Gerador` cp1252 e `oq3d_writer` do `eng-reversa`, uma raiz OQ3D por parte, `PECA` +
`SIMBOLOGIA_3D` + propriedades + `ITEM` com o código — servido por `POST /exportar/aq`
(botão **Exportar .aq**). Verificado na 2831A09 (Inventor, 152 × 107 × 152 mm): 7.506
triângulos no JSON, no `.aq` relido pelo `read_aq.py`/`oq3d.py` e no IFC relido pelo
`parse_ifc.py`, com a mesma bbox e cor. Duas armadilhas da binding OCP dão **segfault sem
traceback**: documento XCAF liberado enquanto os rótulos ainda são usados, e
`ex.Current()` guardado após o `Next()` — ver a skill `leitor-step`.

**IFC também entra pela mesma porta** (`POST /cad/importar`, `/cad/tesselar`, página
`/importar-step`; `/step/*` seguem como aliases): `scripts/ifc_to_geo.py` embrulha o
`parse_ifc.py` do projeto (placements, instâncias, cores por face, B-rep via `ifcopenshell`)
com o `dedup.py` e os metadados do contrato — `partes` (nomes dos `IfcProduct`), `unidade`,
`bbox_mm`. O parser não converte unidade, e o CATIA declara MILLIMETRE escrevendo metros:
a regra é escalar ×0,001 **só** quando o arquivo declara `.MILLI.` **e** a bbox bruta passa
de 50; o que foi feito fica em `escala_aplicada` e nas specs do produto. Verificado: o IFC
exportado da 2CV editada volta com os mesmos 27.937 triângulos; o IFC do STEP, com 7.506.

**Arquivo grande — dois caminhos e importação assíncrona.** Um Revit de 124 MB
(`input/Projeto4.ifc`: um único `IFCBUILDINGELEMENTPROXY`, 733 `IFCCONNECTEDFACESET`,
718.699 faces, 2,5 milhões de entidades) derrubou o fluxo original: o `parse_ifc.py` indexa
o arquivo por regex em Python e levaria minutos e gigabytes; a requisição síncrona estourava
o timeout (300 s do Node, 300 s do Python) e o browser via só **"Failed to fetch"**, sem
nada no log da API — o pedido nunca terminava. Correções, todas em `eb60843`:
- `ifc_to_geo.py` escolhe o caminho: arquivo ≤ 20 MB **com** `IFCTRIANGULATEDFACESET` →
  `parse_ifc.py` (exato, `IFCINDEXEDCOLOURMAP`); senão → `ifcopenshell.geom.iterator`
  (C++, todas as CPUs, `USE_WORLD_COORDS`, cor por material) com dedup vetorizado em numpy.
  No 0.8 do `ifcopenshell`, `style.diffuse.r/g/b` são **métodos** — sem chamar, sai tudo
  cinza. O ifcopenshell descarta triângulos degenerados (27.871 contra 27.937 do exato) e já
  entrega metros mesmo com `MILLIMETRE` declarado (a heurística da escala não dispara — certo).
- `POST /cad/importar` responde **202** na hora com `{importId, statusUrl}` e processa em
  background (`recebido → parseando → gravando → publicado | falhou`), gravando o progresso
  do Python em `BimImport.note`; `GET /cad/importacoes/:id` devolve status, nota, erro e os
  links quando publicado. `?sync=1` mantém o modo antigo para arquivo pequeno e testes.
- Limites: multer 1 GB, Python 30 min, `server.requestTimeout` 60 min. A página envia por
  XHR com progresso e acompanha o status a cada 2 s.

Medido no Projeto4.ifc: `ifcopenshell.open` 13 s, tesselação **221 s** (um só produto, o
multithread não ajuda), **3,6 GB de RSS** no pico, **760.038 triângulos**, JSON de 31 MB no
storage, miniatura em 4,7 s, `1622 × 723 × 1173 mm`. **O editor abre esse modelo em 3 s**
(642 partes por componentes conexos, 141 MB de heap, sem erro). `--max-triangulos` (2 M) não
corta — só põe um `aviso` que a página mostra.

**Como testar** (tudo versionado em `www/tools/`, nada depende do scratchpad de sessão):

```bash
bash www/tools/testes-editor.sh                 # sem browser: round-trip do mesh-model e do exportador IFC (Node + Python)
ROUNDTRIP_SABOTAR=1 bash www/tools/testes-editor.sh   # tem de FALHAR: prova que a métrica do mesh-model acusa erro
ROUNDTRIP_SABOTAR_IFC=1 bash www/tools/testes-editor.sh   # tem de FALHAR: prova que a conferência do IFC exportado acusa erro
node www/tools/e2e/e2e-editor.mjs --validar     # browser (Playwright + SwiftShader): editar, salvar, restaurar, info, IFC, .aq
node www/tools/e2e/e2e-cad-import.mjs input/STEP/2831A09.stp   # importar CAD assíncrono, status, editor
```

O Playwright é o da raiz (`pnpm install`, o mesmo do `scripts/thumbs.mjs`); os testes `.mts`
rodam com `node --experimental-strip-types` (Node ≥ 22.6) sobre uma cópia dos módulos do
web com a extensão `.ts` nos imports — ver o cabeçalho do `testes-editor.sh`.

O round-trip do `mesh-model` compara original e `bake(segment())` **por agrupamento espacial a
≤ 2 µm** (union-find por grade, vértices dos dois lados juntos) e depois triângulo a triângulo
por grupo, com o sentido. Até 2026-09-04 (I13) comparava strings `toFixed(5)` e falhava sempre
(28–32% "fora" em malha idêntica), então o `testes-editor.sh` saía 1 e ninguém olhava. "Vizinho
mais próximo" também não basta: o `dedup` do bake chaveia por posição **e cor**, e dois vértices
a 1,5 µm podem virar dois a 1 µm. `python3 -m pytest tests/test_editor_roundtrips.py` roda o
script e o autoteste sabotado (marcador `paridade`; pula sem Node, sem `three` ou sem storage).

A conferência do **exportador IFC** (etapa Python do mesmo script) pareia cada vértice do
`bake()` esperado com um do IFC lido pelo `parse_ifc.py` a **≤ 2 µm**, nos dois sentidos, e
imprime o desvio máximo — o `real()` do exportador escreve 6 decimais em metros, então o pior
caso teórico é ~1,7 µm. Até 2026-09-05 (I26) comparava conjuntos de coordenadas arredondadas a
10 µm com um limite de 2%: na 20cv da Dancor 2,2% dos pontos caíam na fronteira de arredondamento
com desvio real de 1,37 µm, e o heredoc imprimia `[FALHA]` sem sair 1. Os dois testes usam a
**primeira geometria do storage em ordem alfabética** — importar uma biblioteca nova na POC
troca a fixture (foi assim que o I26 apareceu).

**Pendências desta linha:**
- ~~Miniatura fica desatualizada depois de editar geometria~~ — feito na S7.11 (I14, 2026-09-05):
  `PUT` e `restaurar` chamam `ImportacoesService.regerarMiniatura`, que reaproveita o thumb-worker
  (um Chromium por chamada, alguns segundos) e grava `thumbAtualizadaEm` ou `thumbErro` no produto.
- ~~Voltar ao `.aq`~~ — feito na S7.2 (`scripts/geo_to_aq.py`, botão **Exportar .aq**).
  Falta fechar o ciclo: `.aq` exportado → `build.py` e → import pela POC.
- Montagem STEP com várias peças e cores por face só foi testada sinteticamente.
- Gizmo com várias partes selecionadas gira cada uma em torno do pivô da principal.

### Dependência cruzada com o bilds.com

**A pasta `thumbs/` deixou de ser inerte:** a API do bilds.com (PR #1244, mergeado em
`develop` em 2026-08-28) agora extrai `thumbs/`, grava `thumbBaseUrl` no catálogo e o
viewer usa a imagem pronta em vez de gerar no browser. Consequência prática para este
repo: **um ZIP gerado sem `thumbs/` faz o catálogo voltar ao render dinâmico** — que
funciona, mas é o comportamento de 39,9 s de LCP que motivou toda a mudança. Se o build
avisar que pulou as miniaturas, resolva as dependências antes (ver “Miniaturas
pré-renderizadas”).

### Geometria — corrigida em 2026-08-30, já refletida em tudo

O `oq3d.py` e o `oq3d-parser.ts` emitiam menos geometria do que o `.aq` contém e
deslocavam instâncias rotacionadas. Resolvido (ver S5.1 no histórico) e **propagado**:
o banco da POC foi zerado e recarregado em 2026-08-31, então não há mais geometria do
parser antigo em lugar nenhum. Conferência rápida de que o dado é o novo:

```bash
python3 -c "import json;g=json.load(open('www/storage/bim/geo/<importId>/2cv-t-220-380v-inc-flg-ir3.json'));print(len(g['idx'])//3)"
# 27425 = parser corrigido   |   20452 = parser antigo
```

### Pendência conhecida

- **Deploy do preview na Vercel está sem catálogos** — `output/preview/` passou a ser
  gitignored (511 MB de geometria não entram no histórico), e a Vercel constrói a partir
  do git. Hoje ela serve só a landing. Decidir a estratégia: rodar o `build.py` na
  Vercel, servir a geometria de storage externo, ou aceitar o preview só local.
- **Catálogo não tem visibilidade — fica público no instante em que existe.**
  `bim-catalogs.schema.ts` não tem campo `status`/`visibility`, e
  `catalogos.controller.ts` filtra só por `companyId + slug`. O `publicado` da tabela de
  estado acima é status do *import* (`importacoes.service.ts:210`) — não existe equivalente
  no catálogo. Requisito para a bilds.com, não hardening opcional.

  > Isto **substitui** a antiga finding "GET /geometrias sem auth — adicionar guard".
  > Ela era inaplicável: um `AuthGuard` em `/geometrias` quebra a página pública, porque é
  > o viewer no browser do visitante que busca a geometria, sem token. E
  > `catalogos.controller.ts` também não tem guard — uma requisição anônima já devolve
  > os `geoUrl` de todos os produtos. Enumeração por adivinhação de id não é o risco:
  > `_id` é `crypto.randomUUID()` (`bim-products.schema.ts:8`). Análise completa em
  > `docs/sessoes/S6.1-cache-de-assets.md`, seção 6.
- **`STORAGE_PATH` é variável de ambiente, não commitada.** Está em `www/.env` (gitignored)
  como `STORAGE_PATH=../../storage/bim` (relativo a `apps/api/`). Sem ela a API lê de
  `apps/api/storage` e não encontra as geometrias (o `main.ts` avisa no boot). Um único
  resolvedor, `apps/api/src/common/storage-path.ts`, serve store, workers e logos — até a S7.11
  o controller de empresas usava outro default e os logos iam para uma pasta diferente.

### Variáveis de ambiente — `www/.env`

**O template versionado é `www/.env.example`.** Copie e preencha:

```bash
cp www/.env.example www/.env
```

| Variável | Para quê |
|---|---|
| `MONGODB_URI` | Conexão do Mongo. A POC usou um Atlas M0, mas **nada no código depende do Atlas** — um `mongodb://127.0.0.1:27017` local serve. |
| `MONGODB_DB` | Nome do banco (`bilds-bim-3d`). |
| `SEED_USER` / `SEED_PASSWORD` | Login da POC. **Não consultam o banco** — `auth.controller.ts` compara direto com as variáveis (ADR 7.6). |
| `JWT_SECRET` | Assina o token. Gere com `python3 -c "import secrets; print(secrets.token_hex(32))"`. |
| `STORAGE_PATH` | Onde o `DiskGeometryStore` grava geometria, miniaturas e logos. Relativo ao CWD da API (`www/apps/api`). Resolvida só em `apps/api/src/common/storage-path.ts` (I17); sem ela, `<cwd>/storage` e um aviso no boot. |
| `WEB_ORIGIN` (opcional) | Origem aceita no CORS da API. Padrão `http://localhost:3000`. |
| `PORT` (opcional) | Porta da API. Padrão `4000` (I17, 2026-09-05 — antes era fixa em `main.ts`). |
| `IMPORTACOES_CONCORRENCIA` (opcional) | Quantas importações (`.aq` e CAD) rodam ao mesmo tempo. Padrão `1`: uma fila em memória (`common/fila.ts`); as demais ficam em `recebido` com `na fila — N à frente` no `note`. No boot, imports que a queda anterior deixou abertos viram `falhou` e os uploads temporários são apagados (I11). |
| `NEXT_PUBLIC_API_URL` / `API_URL` (opcionais) | Base da API para o browser e para o servidor Next; no servidor `API_URL` tem precedência. Padrão `http://localhost:4000`. Resolvida em um só lugar, `apps/web/src/lib/api.ts` — `tests/test_www_config.py` acusa qualquer `localhost:4000` fora dele (I17). |
| `JSON_BODY_LIMIT` (opcional) | Limite do body JSON — o `PUT /geometrias/:id` recebe MB. Padrão `300mb`. |
| `PYTHON` (opcional) | Interpretador dos conversores `scripts/{step_to_geo,ifc_to_geo,geo_to_aq}.py`. Padrão `python3`; precisa de `cadquery-ocp` e `ifcopenshell` para STEP e IFC grande. |
| `WORKER_PORT` (opcional) | Porta do servidor HTTP efêmero do `thumb-rasterizer.ts`. Padrão `0` (aleatória). |

O pipeline estático (`scripts/build.py`) **não usa nenhuma delas** — lê só o `.aq`.
A configuração daquele lado é o `config.example.json` da raiz.

### ⚠️ A API não sobe e o Mongoose culpa o whitelist — como saber se é isso mesmo

Documentado em 2026-09-02, depois de perder tempo com isso. O Atlas usado pela POC é um
M0 com **whitelist de IP**, e o IP de uma máquina doméstica ou de escritório muda. Quando
ele muda, a API entra em retry infinito e **não responde a nenhuma requisição**:

```
ERROR [MongooseModule] Unable to connect to the database. Retrying (1)...
MongooseServerSelectionError: Could not connect to any servers in your MongoDB Atlas
cluster. One common reason is that you're trying to access the database from an IP that
isn't whitelisted.
```

**Essa mensagem é um texto fixo do driver, não um diagnóstico** — ela aparece igual para
DNS quebrado, rede bloqueada, cluster pausado, credencial errada e IP não liberado. Não
acredite nela; meça as quatro camadas, de baixo para cima. Rode de `www/apps/api/`, onde
as dependências resolvem:

```bash
cd www/apps/api
NODE_PATH=$(pwd)/node_modules node -e "
require('dotenv').config({path:'../../.env'});
const {MongoClient}=require('mongodb');
new MongoClient(process.env.MONGODB_URI,{serverSelectionTimeoutMS:12000}).connect()
 .then(()=>console.log('CONECTOU'))
 .catch(e=>{console.log(e.name);
   if(e.reason&&e.reason.servers)for(const[k,v]of e.reason.servers)
     console.log(' ',k,'->',v.error?v.error.message.split('\n')[0]:v.type);});"
```

| Camada | Como conferir | Se falha aqui |
|---|---|---|
| DNS SRV | `dns.resolveSrv('_mongodb._tcp.<cluster>.mongodb.net')` | cluster apagado, ou DNS da máquina |
| TCP :27017 | `net.createConnection` no primeiro nó do SRV | firewall ou rede bloqueando saída |
| **TLS** | o comando acima | **é aqui que o whitelist aparece** |
| Autenticação | idem, erro seria `AuthenticationFailed` | usuário ou senha errados |

**A assinatura do IP não liberado é TLS, não autenticação:**

```
tlsv1 alert internal error ... SSL alert number 80
```

nos **três** nós do shard, **com o TCP abrindo normalmente**. O Atlas aceita a conexão e
derruba no handshake — nunca se chega a mandar credencial. Se o TCP conecta e o TLS morre
com alert 80, é whitelist (ou o cluster pausado, que dá o mesmo alert).

**Como resolver:** no Atlas, *Network Access → Add IP Address → Add Current IP Address*.
Descubra o IP com `curl -s https://api.ipify.org`. Num M0, confira também se o cluster não
foi pausado — o Atlas pausa por inatividade e o sintoma é idêntico.

**A API se recupera sozinha:** o `MongooseModule` fica em retry, então depois de liberar o
IP ela conecta no próximo ciclo. Não é preciso reiniciar o processo.

> **Nada no código depende do Atlas** — um `mongodb://127.0.0.1:27017` local serve e
> elimina o whitelist do caminho. O custo é reimportar as bibliotecas, o que exige os
> `.aq` de origem.
