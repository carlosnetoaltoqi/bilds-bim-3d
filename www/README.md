# www — serviço de ingestão + API de catálogo + web

Monorepo pnpm com **três apps e um pacote** (arquitetura em `docs/arquitetura-www-servico-de-ingestao.md`,
2026-09-05, S7.14). Este arquivo é a **fonte de verdade do `www/`**: como subir, contratos, onde está
o quê, estado da base e armadilhas. O `CLAUDE.md` da raiz só aponta para cá.

| App | Porta | O quê |
|---|---|---|
| `apps/ingestao` | 4100 | **Serviço de ingestão**: recebe `.aq`/`.zip` (biblioteca) ou `.stp`/`.step`/`.ifc` (peça), roda o **pipeline Python** (`apps/ingestao/pipeline/`) e o **Chromium** (`thumbs.mjs`) como processos filhos, grava catálogo e produtos no Mongo, geometria e miniaturas no storage. Vai virar um deploy próprio consumido pela bilds.com. |
| `apps/api` | 4000 | **API de catálogo**: empresas, catálogos, produtos, geometria (leitura + edição com copy-on-write) e miniaturas. Sem Python nem Chromium — pede a miniatura nova ao serviço. |
| `apps/web` | 3000 | **Next**: página pública do catálogo (cards com miniatura, modal com 3D) com a chamada para edição, editor de produto (informações + 3D + exportar IFC/`.aq`), `/importar`. |
| `packages/dominio` | — | `@bim/dominio`: schemas Mongoose, storage em disco, contrato `{pos,col,idx}`, ETag, validação, nome de upload — o que api e ingestao compartilham. Fonte TypeScript compilada dentro de cada app. |

**POC enquanto viver neste repositório: sem auth, sem admin.** A empresa é só um agrupador de
catálogos, escolhida por `customUrl` no import. Login, JWT e o middleware do Next saíram na E1.

## Subir

```bash
cp .env.example .env            # e preencher (Mongo, STORAGE_PATH; o resto tem padrão)
pnpm install
pnpm dev:ingestao               # http://localhost:4100
pnpm dev:api                    # http://localhost:4000   (outro terminal)
pnpm dev:web                    # http://localhost:3000   (outro terminal)
```

Requisitos além do Node/pnpm (o `bash scripts/bootstrap.sh --check` da raiz confere tudo): Python 3.12 com
`numpy` (ler `.aq`), Chromium do Playwright (`pnpm install` na raiz roda `playwright install chromium`;
libs `libnss3 libnspr4 libasound2t64`) e, só para CAD, `cadquery-ocp` + `ifcopenshell`
(`pip install --user --break-system-packages -r requirements-cad.txt`).

Se o serviço ou a API ficarem em `Retrying (n)...` com o Mongoose culpando o whitelist, é o IP no
Atlas — ver "A API não sobe e o Mongoose culpa o whitelist", no fim.

## Contratos

### Serviço de ingestão — `:4100`

| Rota | O quê |
|---|---|
| `POST /importacoes` | multipart `file` + campos opcionais `empresa` (customUrl; vazio = a primeira), e para peça CAD `fabricante`, `catalogo`, `nome`, `deflexao` (mm, só STEP). Tipo pela extensão. → **202** `{importId, tipo, status:'recebido', statusUrl}` |
| `GET /importacoes/:importId` | `{status, tipo, note, error, productCount, thumbCount, thumbFailed, thumbError, diag, catalogSlug, catalogTitle, empresa, catalogoUrl, editorUrl, segundos…}`; CAD publicado traz `produtoId`, `nome`, `thumbUrl` e o `editorUrl` do produto |
| `GET /importacoes?empresa=&limite=` | últimas importações (padrão 20, máx. 100) |
| `DELETE /importacoes/:importId` | apaga uma importação **terminada**: produtos dela, `geo/<importId>`, `thumbs/<importId>`, documento; o catálogo fica, recontado. **409** se ainda está em `recebido`/`parseando`/`gravando` |
| `POST /miniaturas/regerar` `{productId}` | 202 `{productId, naFrente}` — renderiza a miniatura do produto e grava `thumbKey`/`thumbAtualizadaEm` ou `thumbErro`. Quem chama é a API depois de editar geometria |
| `POST /cad/tesselar` | multipart `.stp/.step/.ifc` (+ `deflexao`) → `{pos, col, idx, partes, unidade, bbox_mm, …}` síncrono — consumido pela página `/cad` do web (a conversão saiu do editor em 2026-09-05) |
| `POST /exportar/aq` | JSON `{info, partes[] \| pos,col,idx}` → download do `.aq` (`geo_to_aq.py`); resumo no header `X-Aq-Resumo` |
| `GET /exportar/catalogo/:catalogId` | download do **catálogo salvo como um `.aq` novo** (`catalogo_to_aq.py`, S7.16): todas as peças como estão na tela (as apagadas não vão; as editadas vão editadas, geometria inclusive), um grupo por série, simbologia compartilhada preservada, uma propriedade por chave de spec, curva Q-H. Gerado do zero (o `.aq` original não fica no servidor), stream e apagado — nada fica. Síncrono: Amanco 854 peças → 54 MB em 7 s. Nome `pecas_<Fabricante>_<Título>.aq`; resumo em `X-Aq-Resumo`. **404** catálogo inexistente, **400** sem produtos, **500** com o stderr do Python (geometria ausente, caractere fora do cp1252) |
| `GET /health` | 200 `{status, mongo, pipeline}` ou 503 pela conexão do Mongoose |

Estados de uma importação: `recebido → parseando → gravando → publicado | vazio | falhou`. As
miniaturas rodam **depois** de `publicado`, ainda na vaga da fila, e nunca mudam o status: o
resultado vai para `thumbCount`/`thumbFailed`/`thumbError` e uma linha no `note`. `note` também
carrega a posição na fila (`na fila — N à frente`) e o progresso do Python (`[  8.5s] 200
geometrias gravadas (200/457 simbologias)`).

Uma importação por vez (`IMPORTACOES_CONCORRENCIA`, padrão 1): um Python e depois um Chromium. A
regeneração de miniatura tem fila própria (concorrência 1) para não esperar um import de minutos.
No boot, imports não terminais viram `falhou` (`a API foi reiniciada durante a importação`), a
`geo/<importId>/` é apagada e os uploads temporários também.

### API de catálogo — `:4000`

| Rota | O quê |
|---|---|
| `GET /empresas` · `POST /empresas` (multipart `name`, `customUrl`, `logo?`) · `GET /empresas/:customUrl` · `GET /empresas/:customUrl/catalogos` · `GET /logos/:companyId` | empresas e seus catálogos |
| `DELETE /empresas/:customUrl` · `DELETE /catalogos/:id` · `DELETE /produtos/:id` | **apagar em cascata** (`packages/dominio/src/remocao.ts`): empresa leva catálogos, produtos, imports, storage e logo; catálogo leva produtos, `geo/`+`thumbs/` dos imports que o alimentaram e os imports; produto leva a geometria e a miniatura **só se nenhum outro produto as compartilha** (mais a cópia copy-on-write e o `.orig.json`), e reconta o catálogo. Resposta: `{ok, produtos, catalogos, imports, arquivos[], avisos[]}` |
| `GET /catalogos/:empresa/:slug[?serie=]` · `PATCH /catalogos/:id` | página pública (produtos com `geoUrl`/`thumbUrl`) e edição de título/fabricante/layout |
| `GET /produtos/:id` · `PATCH /produtos/:id` | informações do produto (nome, série, specs, curva, potência, conexões); `infoOriginal` na primeira edição; `thumbAtualizadaEm`/`thumbErro` |
| `GET /geometrias/:id` · `GET …/original` · `PUT /geometrias/:id` · `POST …/restaurar` | geometria com ETag/304. **PUT**: geometria exclusiva → `.orig.json` ao lado; geometria **compartilhada** (o pipeline grava uma por simbologia) → **copy-on-write**: `geo/<importId>/<productId>.json` só do produto, chave compartilhada em `geoKeyCompartilhada`. Os dois pedem a miniatura ao serviço; resposta traz `miniatura: 'regerando' \| 'nao-solicitada'` |
| `GET /thumbs/:id` | miniatura WebP com ETag/304 (`thumbs/<importId>/<stem da geometria>.webp` — produtos que compartilham geometria compartilham a imagem) |
| `GET /health` | 200/503 |

### Web — `:3000`

| Página | O quê |
|---|---|
| `/` | empresas e catálogos com **ver** / **editar** / **apagar** / **importar para esta empresa**, **apagar empresa**; menu: **Importar biblioteca .aq**, **Importar peça STEP / IFC**, **Converter peça CAD**, **Criar empresa** |
| `/importar[?empresa=&tipo=aq\|cad]` | sobe `.aq`/`.zip`/`.stp`/`.step`/`.ifc` (`tipo` restringe; progresso de upload, campos CAD só quando o arquivo é CAD), acompanha o status a cada 2 s, lista as últimas importações com **apagar** (só as terminadas) |
| `/cad` | converte `.stp`/`.step`/`.ifc` pelo serviço (`POST /cad/tesselar`) sem criar produto: viewer 3D, unidade/bbox/sólidos/triângulos, download em JSON, IFC4 (browser) ou `.aq` (`POST /exportar/aq`); link para importar como produto |
| `/:empresa/:catalogo` | página pública: cabeçalho com **editar catálogo**, cards com miniatura pré-gerada, modal com viewer 3D e **Editar informações e modelo 3D →** |
| `/:empresa/:catalogo/editar` | metadados do catálogo, **baixar .aq (AltoQi Builder)** — o catálogo salvo vira uma biblioteca `.aq` nova para adicionar no Builder (`GET /exportar/catalogo/:id` do serviço) —, **apagar catálogo**, lista de produtos com **Editar** / **apagar** (importar só pelo menu da página inicial) |
| `/:empresa/:catalogo/editar/:produtoId` | editor: viewport 3D (selecionar, mover, girar, espelhar, primitivas, STL/OBJ/JSON locais), informações, exportar IFC4 (no browser) e `.aq` (pelo serviço), salvar (`PUT /geometrias`), restaurar, **apagar peça**. **STEP/IFC não entram pelo editor** desde 2026-09-05: viram produto pela página inicial |
| `/empresa/criar` | nome, customUrl, logo |

O web fala **direto** com os dois serviços (CORS `WEB_ORIGIN`): `lib/api.ts` é o único lugar com
`API_URL` e `INGESTAO_URL` — `tests/test_www_config.py` acusa qualquer URL fixa fora dele.

## Fluxo de uma importação de `.aq` (o que acontece por dentro)

```
web ──multipart──► POST /importacoes ──► BimImport{recebido, tipo:'aq'} ──► Fila
  vaga ──► parseando: python3 pipeline/catalogo_de_aq.py <aq> --geo-dir storage/geo/<importId> --saida tmp.json --sair-com-stdin
                     (stderr = progresso → note; uma geometria por simbologia; dedup float32)
       ──► gravando: upsert BimCatalog (companyId+slug) · insertMany BimProduct{geoKey: geo/<importId>/<geo>.json}
                     · produtos e geo/thumbs do import anterior do mesmo slug apagados
       ──► publicado (diag do pipeline no import)
       ──► miniaturas: node pipeline/thumbs.mjs cfg.json  (Chromium + harness.html + three.module.js do app)
                     uma linha JSON por geometria → thumbKey em cada produto que a usa → thumbCount/thumbFailed
```

Medido em 2026-09-05 (S7.14, WSL2): Dancor 13 produtos/13 geometrias — parse 7,6 s, miniaturas 3 s;
**Amanco 856 produtos/448 geometrias — parse 22 s, miniaturas 37 s, total 58 s** (o caminho anterior,
em TypeScript, levava ~80 s só nas miniaturas).

Os filhos recebem o `stdin` em pipe e **saem quando o pai morre** (`processo.py:vigiar_stdin`,
`sairComStdin` no `thumbs.mjs`): um `kill -9` no serviço com o Python a meio caminho não deixa
órfão gravando em `geo/` (verificado na S7.14; antes do I29 deixava).

## Testes

```bash
python3 -m pytest -q                                 # na raiz: 102 testes (≈ 60 s; 2 abrem o Chromium)
python3 -m pytest -q -m "not thumbs"                 # o que o CI roda
bash tools/testes-editor.sh                          # round-trips do editor sem browser (mesh-model, IFC)
node tools/e2e/e2e-editor.mjs --validar              # editor no browser (Playwright + SwiftShader), com os três apps de pé
node tools/e2e/e2e-cad-import.mjs ../input/STEP/2831A09.stp   # importar CAD pelo serviço e abrir no editor
```

Os testes de `www/` em `tests/` (marcador `paridade`) rodam os harnesses `.cts`/`.mts` de
`tests/paridade/` com o `ts-node` de cada app — pulam se `pnpm install` não foi feito. O que eles
provam está na tabela de testes do `CLAUDE.md`. Ainda **não há** teste automatizado que suba os
serviços com Mongo: o teste de aceitação da S7.14 (import Dancor e Amanco, edição, copy-on-write,
`kill -9`) está registrado em `docs/sessoes/S7.14-www-servico-de-ingestao.md`.

## Onde está o quê

| Pasta | Conteúdo |
|---|---|
| `apps/ingestao/src/importacoes/` | `importacoes.service.ts` (o fluxo acima, CAD e regeneração de miniatura), controller, `importar.dto.ts`, `fila.ts`, `recuperacao.service.ts` |
| `apps/ingestao/src/pipeline/` | `processo.ts` (spawn com timeout, ociosidade, stdin em pipe, `ProcessoError`) e `pipeline.service.ts` — a ÚNICA fronteira com Python/Node |
| `apps/ingestao/src/{cad,miniaturas,health}/` | `POST /cad/tesselar`, `POST /exportar/aq`, `POST /miniaturas/regerar`, `GET /health` |
| `apps/ingestao/pipeline/` | **o pipeline Python** + `thumbs.mjs`/`harness.html` + escritor de `.aq`/OQ3D (README próprio; autocontido desde I4); o `scripts/build.py` da raiz importa daqui |
| `apps/api/src/{empresas,catalogos,produtos,geometrias,thumbs,health}/` | um módulo Nest por assunto; `common/ingestao-client.ts` fala com o serviço |
| `apps/web/src/app/` | `page.tsx` (home), `importar/`, `[empresa]/[catalogo]/…`, `empresa/criar/` |
| `apps/web/src/components/bim-catalog/` | viewer público: cards, modal, `bim-viewer-engine.ts` (`buildScene` — a mesma cena do `harness.html`) |
| `apps/web/src/components/bim-editor/` | editor: `mesh-model.ts` (puro), `EditorViewport.tsx`, `GeometryPanel.tsx`, `InfoForm.tsx`, `ifc-export.ts`, `ProductEditor.tsx` |
| `packages/dominio/src/` | `schemas/`, `storage-path.ts`, `geometry-store/`, `geo-buffers.ts`, `asset-cache.ts`, `validation.ts`, `upload.ts`, `mongo-pronto.guard.ts` (I32), `remocao.ts` (apagar em cascata) |
| `tools/` | `testes-editor.sh`, `roundtrip-*.mts`, `e2e/` |
| `storage/bim/` | `geo/<importId>/`, `thumbs/<importId>/`, `logos/` — gitignored, regenerável por import |

## Estado da base e do storage (2026-09-05, fim da S7.16)

Zerado no fim da S7.15 (coleções dropadas, `www/storage/bim/`, `output/` e `eng-reversa/saida/`
apagados) e **recarregado pelo usuário** em seguida: **2 empresas** — `amanco` com o catálogo
`esgoto-sn-sr-silentium` (854 produtos: o `.aq` tem 856 com 3D, 2 `Cap 50mm` foram apagadas na
interface; 457 geometrias em `geo/b9f20e3d…`) e `acme` com `pecas-ifc` (1 produto, `Projeto4.ifc`,
760 mil triângulos). Storage: `geo/` 211 MB, `thumbs/` 2,9 MB.

Para carregar: subir os três apps, criar uma empresa em `/empresa/criar`, importar em `/importar`
(`input/` tem 16 `.aq`, gitignored). Reimportar um `.aq` **substitui** o catálogo de mesmo slug na
empresa (ids de produto mudam). Para zerar de novo: dropar as quatro coleções e apagar
`www/storage/bim/{geo,thumbs,logos}`.

Lembrete sobre os dois modelos de geometria que a API aceita: catálogos do pipeline Python têm uma
geometria **por simbologia**, compartilhada entre produtos (copy-on-write ao editar); o `geoKey`
aponta para `geo/<importId>/<stem>.json` e a miniatura para `thumbs/<importId>/<stem>.webp`.

## Decisões e pendências

- **Por que Python e não o port TS** (A2): o caminho `read_aq.py`/`oq3d.py`/`thumbs.mjs` é o que está
  em produção no ZIP da bilds.com; o port TS não se provou eficiente nas miniaturas e foi removido
  na E3. Paridade Python ↔ TS deixou de existir porque não há mais TS lendo `.aq`.
- **Por que a casca é Nest** (A3): reaproveita fila, recuperação, validação (`ValidationPipe` + DTOs)
  e o nome UTF-8 do upload, endurecidos em S7.11–S7.13.
- **`pnpm start` do `dist/` não roda**: o `tsc` trata o symlink `@bim/dominio` como pacote externo
  e não o emite. Só o modo dev (`ts-node`) funciona. Resolver quando o serviço for isolado
  (compilar o `dominio` para `dist` com `main` próprio, ou `paths` + bundler).
- **Sem visibilidade de catálogo**: publicado = público na hora. Requisito da bilds.com, não daqui.
- **Mongo fora**: `MongoProntoGuard` (`@bim/dominio`, `APP_GUARD` nos dois apps) responde **503 na hora** em toda rota menos `/health` enquanto a conexão não está pronta (I32, S7.15).
- **Nest 10**: o multer embutido decodifica o nome do arquivo em latin1 (`upload.ts` corrige); subir
  para o Nest 11 traria o multer novo.
- `tools/e2e/*.mjs` foram apontados para o serviço mas **não foram reexecutados** na S7.14.
- **Não rode `pnpm -r build` com o `next dev` de pé**: o `next build` sobrescreve o `.next/` que o dev
  server está usando e toda página passa a responder 500 (`Cannot find module './837.js'`) até
  reiniciar o `pnpm dev:web` (aconteceu na S7.16). O `tsc --noEmit` em `apps/web` é seguro.

## Variáveis de ambiente — `www/.env`

**O template versionado é `www/.env.example`.** Copie e preencha (`cp www/.env.example www/.env`).

| Variável | Para quê |
|---|---|
| `MONGODB_URI` · `MONGODB_DB` | Conexão e nome do banco. A POC usa um Atlas M0, mas **nada no código depende do Atlas** — `mongodb://127.0.0.1:27017` serve. Os dois serviços usam a mesma base. |
| `STORAGE_PATH` | Onde geometria, miniaturas e logos ficam. Relativo ao CWD de cada app (`apps/api`, `apps/ingestao`) — `../../storage/bim` dá `www/storage/bim` nos dois. Resolvida só em `packages/dominio/src/storage-path.ts`; sem ela, `<cwd>/storage` e um aviso no boot. |
| `PORT` · `INGESTAO_PORT` (opcionais) | Portas da API (4000) e do serviço (4100). |
| `INGESTAO_URL` · `NEXT_PUBLIC_INGESTAO_URL` (opcionais) | Onde a API e o web acham o serviço. Padrão `http://localhost:4100`. |
| `API_URL` · `NEXT_PUBLIC_API_URL` (opcionais) | Onde o web acha a API. Padrão `http://localhost:4000`. |
| `WEB_ORIGIN` (opcional) | Origem aceita no CORS dos dois serviços. Padrão `http://localhost:3000`. |
| `IMPORTACOES_CONCORRENCIA` (opcional) | Importações simultâneas no serviço (1–8, padrão 1). |
| `JSON_BODY_LIMIT` (opcional) | Limite do body JSON (`PUT /geometrias`, `POST /exportar/aq`). Padrão `300mb`. |
| `PYTHON` (opcional) | Interpretador do pipeline. Padrão `python3`; precisa de `numpy`, e de `cadquery-ocp` + `ifcopenshell` para CAD. |
| `PIPELINE_DIR` (opcional) | Onde está `pipeline/`; só quando o serviço roda fora do repositório. |
| `BILDS_THREE_DIR` (opcional) | Pasta com `three.module.js` para o harness; padrão: o `three` instalado em `apps/ingestao`. |

O pipeline estático (`scripts/build.py`) **não usa nenhuma delas** — lê só o `.aq`.

## ⚠️ A API não sobe e o Mongoose culpa o whitelist — como saber se é isso mesmo

Documentado em 2026-09-02, depois de perder tempo com isso. O Atlas usado pela POC é um
M0 com **whitelist de IP**, e o IP de uma máquina doméstica ou de escritório muda. Quando
ele muda, a API (e o serviço) entram em retry infinito e **não respondem a nenhuma requisição**:

```
ERROR [MongooseModule] Unable to connect to the database. Retrying (1)...
MongooseServerSelectionError: Could not connect to any servers in your MongoDB Atlas
cluster. One common reason is that you're trying to access the database from an IP that
isn't whitelisted.
```

**Essa mensagem é um texto fixo do driver, não um diagnóstico** — ela aparece igual para
DNS quebrado, rede bloqueada, cluster pausado, credencial errada e IP não liberado. Não
acredite nela; meça as quatro camadas, de baixo para cima. Rode de `www/apps/api/`, onde
as dependências resolvem (o driver é o `mongoose.mongo` — não instale o pacote `mongodb`):

```bash
cd www/apps/api
NODE_PATH=$(pwd)/node_modules node -e "
require('dotenv').config({path:'../../.env'});
const {MongoClient}=require('mongoose').mongo;
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
com alert 80, é whitelist (ou o cluster pausado, que dá o mesmo alert). Libere em Network
Access → Add Current IP Address (`curl -s https://api.ipify.org`); os serviços reconectam
sozinhos. Para simular "Atlas fora" sem mexer na whitelist: proxy TCP com TLS+SNI, receita em
`docs/sessoes/S7.13-teste-de-aceitacao-www.md` §3.

## Histórico

O que este `www/` foi antes (POC de catálogo dinâmico S0–S5.2, POC de edição S7.1–S7.2, port TS
do leitor `.aq`, medições de miniatura, login por seed) está em `docs/sessoes/` e nos aprendizados
destilados em `docs/solutions/architecture-patterns/`. A S7.14 registra a reestruturação.
