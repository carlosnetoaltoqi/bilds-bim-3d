# Auditoria de pendências de sistema — 2026-09-03

**Motivo.** Início da fase "passar o projeto a limpo". Diretriz do usuário: os catálogos
gerados são POC e não são consumidos por ninguém; podem ficar errados **desde que a
geração acuse o erro** e que código e conhecimento sejam corrigidos. O valor está no
código e na documentação, não na saída.

**Método.** Quatro varreduras independentes, somente leitura, na branch `poc-edicao`
(topo `50cb484`): pipeline estático (`scripts/`, `templates/`, `eng-reversa/`), POC
dinâmica (`www/`), documentação (CLAUDE.md, README, docs/, skills, CONCEPTS) e higiene
do repositório/infra. Cada achado traz evidência reproduzida; os quatro críticos de
código foram reproduzidos uma segunda vez antes de fechar este documento.

**Efeitos colaterais da auditoria** (nenhum arquivo versionado alterado):
- Mongo/storage: import `dd393c56` ("auditoria-e2e") criado no catálogo `pecas-step`
  pelo `e2e-cad-import.mjs`; produto `dd73f0b2` (2CV) ficou com `editadoEm` e
  `infoOriginal` preenchidos pelo `e2e-editor.mjs` (geometria restaurada).
- `output/preview/pvc-construcao-civil/` regenerado pelo build de teste (mesmo conteúdo).

---

## Índice por severidade

| ID | Item | Área |
|---|---|---|
| **C1** ✅ | Aspas em nome de série quebram `data-filter`/`onclick` (6 catálogos gerados) — **corrigido 2026-09-03** | geração |
| **C2** ✅ | `read_aq.open_aq` cria `.aq` vazio quando o caminho não existe e mascara o erro — **corrigido 2026-09-03** | geração |
| **C3** ✅ | `build.py` sempre sai com código 0, mesmo sem produto ou com falhas em `--all` — **corrigido 2026-09-03** | geração |
| **C4** ✅ | Build da API (`tsc -p`) quebrado por erro de tipo em `tools/aq-reader.ts:203` — **corrigido 2026-09-03** | www |
| **C5** ✅ | Branch `poc-edicao` (12 commits, ~6.300 linhas) existe só nesta máquina — **corrigido 2026-09-03** (S7.5, push após a reescrita) | repo |
| **C6** ✅ | 398 MB de geometria morta (`output/preview/**`) no histórico git e no GitHub — **corrigido 2026-09-03** (S7.5, `git filter-repo` + force-push) | repo |
| **C7** | Deploy da Vercel é irreproduzível: serve o `output/preview` local desta máquina | infra |
| **C8** ✅ | Diagnóstico do CLAUDE.md manda usar `latin-1`; o correto é cp1252 — **corrigido 2026-09-03** | docs |
| **C9** | README ensina fluxo de publicação que não publica nada | docs |
| **C10** | Estado da base aparece em três versões contraditórias no CLAUDE.md | docs |
| I1 ✅ | Miniaturas degradam em silêncio no build (ZIP sem `thumbs/`, exit 0) — **corrigido 2026-09-03** (S7.6: `ThumbsError`, `--allow-no-thumbs`, `thumbCount`) | geração |
| I2 ✅ | Geometria inválida/vazia contabilizada como "tubos/kits"; `_read_mesh` muda — **corrigido 2026-09-03** (S7.6: `diag` por categoria; `_read_mesh` lança em truncado; **bônus: malha versão 3 da Maxbar, 56 peças recuperadas**) | geração |
| I3 ✅ | `OQ3DAvisoParse` não chega ao operador — **corrigido 2026-09-03** (S7.6: coletado por simbologia, `resumo_diag`) | geração |
| I4 | `scripts/geo_to_aq.py` depende de `eng-reversa/tools/` (estudo) | geração |
| I5 | `requirements.txt` incoerente; OCP/ifcopenshell/pypdf fora de qualquer requirements | ambiente |
| I6 | Modo `--ifc` do build é código morto (~450 linhas) com `config.example.json` obsoleto | geração |
| I7 | Fallback sem Jinja2 gera HTML quebrado | geração |
| I8 | `oq3d_roundtrip.py` pula o caso real (caminho errado) e reporta sucesso | testes |
| I9 ✅ | Não há suíte de testes do pipeline; `validar_aq.py` é específico da Akato — **suíte criada 2026-09-03** (S7.6: `tests/`, 43 testes, paridade py ↔ ts); a parte do `validar_aq.py` segue em aberto como L-item | testes |
| I10 | Rotas de escrita/conversão sem auth, body 300 MB, upload 1 GB, python sem concorrência | www |
| I11 | Importação assíncrona sem fila nem recuperação após restart | www |
| I12 | `@nestjs/mongoose@12` sobre Nest 10 (peer violada); dois drivers Mongo | www |
| I13 | `testes-editor.sh` falha sempre (métrica de round-trip errada), não sinaliza nada | testes |
| I14 | Miniatura desatualizada após editar geometria | www |
| I15 | Erros de processo filho engolidos (`type:'error'` do thumb-worker; promise presa) | www |
| I16 | Validação de entrada 100% manual, sem `ValidationPipe` | www |
| I17 | `http://localhost:4000` hardcoded em 3 páginas; porta fixa; dois defaults de `STORAGE_PATH` | www |
| I18 | npm + pnpm na raiz, dois lockfiles versionados | repo |
| I19 | Zero pins de versão (Node/pnpm/Python); heurística no `build.py` compensa | repo |
| I20 | Sem CI, LICENSE, `.editorconfig`, `.gitattributes` | repo |
| I21 ✅ | `.git` com 6.867 objetos soltos, nunca `gc` — **resolvido 2026-09-03** pelo repack do filter-repo (1,3 MB em pack) | repo |
| I22 | CLAUDE.md com 2.797 linhas, 41% histórico, 7 notas "versões antigas diziam" | docs |
| I23 | Onze afirmações do CLAUDE.md/README quebradas ou desatualizadas (tabela abaixo) | docs |
| I24 | Skills e CLAUDE.md com conhecimento só de um lado; regra "mesmo commit" nunca cumprida | docs |
| I25 | `docs/plano-produto-dinamico.md` não marcado histórico; §11 incompleto; §13 com tabela quebrada | docs |
| L1–L14 | Limpeza (duplicações, código legado, `any`, funções gigantes, etc.) | todas |

---

## Críticos

> C1–C4 e C8 corrigidos em 2026-09-03 (S7.4); C5 e C6 em 2026-09-03 (S7.5). O texto abaixo
> descreve o estado **antes** da correção; a verificação está nas entradas S7.4 e S7.5 do
> `CLAUDE.md`. **Os SHAs citados neste documento são os pós-reescrita** — o mapa
> antigo → novo está em `docs/sessoes/S7.5-push-e-reescrita-do-historico.md`.

### C1. Aspas no nome de série quebram o filtro HTML
- `templates/layouts/series-rows.html:242` e `catalog-grid.html:183`:
  `data-filter="{{ f }}" onclick="filterBy('{{ f }}',this)"` com `autoescape=False`
  (`build.py:569-573`).
- Evidência: `output/preview/bombas-pressurizadores-series/index.html` contém
  `data-filter="1" x 1"" onclick="filterBy('1" x 1"',this)"`. 60 ocorrências em 6 slugs
  (Komeco bombas-pressurizadores ×3, Maxbar barramento-blindado ×3). Atributo truncado,
  `onclick` com erro de sintaxe.
- Correção: `{{ f | e }}` no atributo, `onclick` substituído por listener que lê
  `dataset.filter`; ligar `autoescape` fora do bloco `<script>`. Teste de render com série
  contendo `"` e `'`.

### C2. `open_aq` cria um `.aq` vazio e mascara "arquivo não existe"
- `scripts/read_aq.py:54` (`sqlite3.connect` cria o arquivo), `:59` (`except: pass`),
  `:69` (mensagem "não é SQLite nem ZIP"). `peek_metadata` (`:278-281`) engole tudo e
  devolve fabricante vazio.
- Reproduzido: `open_aq('nao_existe.aq')` → `ValueError` e um arquivo de 0 bytes criado.
- Correção: `FileNotFoundError` antes de conectar; abrir com
  `sqlite3.connect(f'file:{p}?mode=ro', uri=True)`.

### C3. `build.py` sempre termina com exit 0
- `build.py:1415-1417` (zero produtos → imprime ERRO e retorna), `:1573-1579` (`main`
  segue e imprime "Build concluído"), `:1502-1511` (`run_all` lista `falhas` e não sai
  com 1). Com `--skip-zip` o resumo diz "gerados : 0" porque conta ZIPs.
- Correção: `sys.exit(1)` nos dois pontos; contar builds concluídos.

### C4. Build da API quebrado
- `apps/api/package.json:7` → `tsc -p tsconfig.json`, sem `include`; o import
  `../../../../tools/aq-reader` (`parse-worker.ts:13`) entra na compilação e falha:
  `aq-reader.ts(203,16): error TS2352`. O `dev` não sofre (`ts-node transpile-only`).
- Correção: tipar o `.map` (ou `as unknown as AqCurvaPonto[]`) e acrescentar `include`
  ao tsconfig; rodar `pnpm -r build` no CI.

### C5. `poc-edicao` sem backup
- `git ls-remote --heads origin` → só `main`. 12 commits à frente, incluindo skill
  `leitor-step`, `www/README.md`, três conversores.
- Correção: `git push -u origin poc-edicao` imediatamente; depois decidir merge em `main`.

### C6. Geometria morta no histórico git
- 397,6 MB / 958 blobs de `output/preview/**` (mais um `.aq` de 6,7 MB de
  `eng-reversa/saida/`) em commits de "build: catálogo…"; removidos da árvore em
  `130cb5b`, `237e247`, `2166c96`, `eb21380` mas presentes em `origin/main`. `.git` sem
  nenhum pack (I21).
- Correção: decidir se reescreve o histórico (`git filter-repo --invert-paths`) e
  force-push coordenado, ou aceita o peso. Só depois rodar `git gc`.
- **Feito na S7.5:** reescrita com `--invert-paths --path-regex '^output/preview/[^/]+/'
  --path eng-reversa/saida/`, preservando `output/preview/{index.html,.gitignore,.gitkeep}`;
  `.git` de 137 MB → 1,6 MB; `main` e `poc-edicao` reenviadas com `--force`.

### C7. Deploy Vercel irreproduzível
- `vercel.json` → `outputDirectory: output/preview` (gitignored). Commit `dd9f943`
  desconectou a integração git; deploy é `vercel --prod` do conteúdo local (2,1 GB).
  Nenhum outro clone reproduz ou reverte. CORS `*` global sem justificativa registrada.
- Correção: script `deploy.sh` (`build.py --all` + `vercel --prod`) com manifesto do que
  foi ao ar (slugs + hash + data) versionado; ou preview só local. Restringir CORS a
  `**/data/*.json` e `thumbs/`.

### C8. Diagnóstico manda usar `latin-1`
- `CLAUDE.md:1538` "Texto com lixo → usar `latin-1`" contradiz `CLAUDE.md:1206`
  ("cp1252, não latin-1") e o próprio histórico (2450). É a regressão corrigida em
  2026-08-28, ainda na tabela que se consulta primeiro.

### C9. README ensina a publicar de um jeito que não publica
- `README.md:104-114`: "push para `main` dispara o deploy… `git add output/preview/`".
  `output/preview/*` é gitignored e a integração git está desligada.

### C10. Estado da base em três versões
- `CLAUDE.md:94-110` (1 empresa, 3 catálogos, 18 produtos, recarregado 09-03) vs
  `181-183` ("zerado desde 2026-09-02… `.aq` de origem não estão nesta máquina") vs
  `124-125` ("`input/` tem os 15 `.aq`…"). Também `102-104` diz 6 imports; o disco tem 9
  (e agora 10, com o resíduo desta auditoria). `input/` tem 16 `.aq`, não 10 nem 15.

---

## Importantes — geração e testes

- **I1.** ✅ (S7.6) `build.py:691-693, 719-745`: sem Node/Playwright o passo de miniaturas vira
  AVISO e o ZIP sai sem `thumbs/` com exit 0 — o cenário que devolve 39,9 s de LCP na
  bilds.com. Falhar por padrão; `--allow-no-thumbs` explícito; `thumbCount` no manifest.
  *Feito exatamente assim; também falha quando parte das miniaturas não renderiza.*
- **I2.** ✅ (S7.6) `build.py:354-355` (blob sem assinatura OQ3D → `continue`), `:361-362` (`pos`
  vazio → `continue`), `:410-412` (somados em `sem_3d` como "tubos/kits").
  `oq3d._read_mesh:301-315` devolve offset em malha malformada sem sinal, enquanto o port
  TS lança `OQ3DError`. Contar separadamente e emitir `OQ3DAvisoParse`.
  *Feito. O contador separado revelou que a Maxbar tinha 31 simbologias "vazias": malhas
  de versão 3, que nenhum dos dois parsers aceitava. Corrigido nos dois (`MESH_VERSOES`).*
- **I3.** ✅ (S7.6) `oq3d.py:263-269` usa `warnings.warn`; o filtro padrão mostra só a 1ª por local e
  `build.py` não agrega. `catch_warnings(record=True)` por simbologia e linha no resumo.
  *Feito exatamente assim (`resumo_diag`).*
- **I4.** `scripts/geo_to_aq.py:54-60` importa `gerar_aq`, `oq3d_writer` e lê
  `eng-reversa/dados/schema-aq-607.sql`; é chamado pela API (`step.service.ts:23-24`).
  Promover para `scripts/aq_writer.py` + `scripts/schema-aq-607.sql`; `eng-reversa`
  importa de `scripts/`.
- **I5.** `requirements.txt` puxa `ifcopenshell` por padrão embora o comentário diga
  "opcional"; `cadquery-ocp` só em comentário; `pypdf` (usado por
  `eng-reversa/tools/pdf_coords.py`) em nenhum requirements; `pillow` e `shapely`
  instalados sem uso declarado. Tudo em `~/.local` com `--break-system-packages`, sem venv.
  Separar `requirements.txt` (jinja2, numpy) de `requirements-cad.txt` (pins).
- **I6.** Modo `--ifc` (~450 linhas em `build.py`) sem fixture: `config.example.json`
  cita `input/pecas_dancor.aq` e `CAM-W10.IFC` inexistentes; `input/README.md` está
  dentro de pasta gitignored; `scan_input:1078` devolve `'flat'` onde a doc diz `'subdir'`;
  `parse_ifc.py:9` cita `parse_one()` que não existe. Mover para `scripts/legacy/` com IFC
  pequeno de fixture, ou remover.
- **I7.** `build.py:576-580`: fallback sem Jinja2 só substitui `{{ catalog | tojson }}`,
  mas os templates usam `{% for %}`. Abortar com mensagem clara.
- **I8.** `eng-reversa/tools/oq3d_roundtrip.py:200-201` aponta
  `input/Amanco/PVC Esgoto SN, SR e Silentium/…aq`; o real é `input/Amanco/…aq`. Saída
  "6. pulado" e exit 0.
- **I9.** ✅ suíte (S7.6) — `validar_aq.py` segue Akato-específico. Nenhum `tests/`, `test_*.py`, pytest. `validar_aq.py:239-244` exige 1:1
  peça→simbologia e tubos de 600 cm — a Komeco (válida) dá 18/20 e exit 1. Criar `tests/`
  com o `.aq` da Akato (7 MB, gerado pelo projeto) como fixture: `open_aq`, `extract`,
  `to_buffers`, `dedup`, `build_catalog_from_aq`, render dos dois layouts com série
  contendo aspas, e **paridade** `oq3d.py` ↔ `oq3d-parser.ts` e `read_aq` ↔ `aq-reader`
  byte a byte.
- **I13.** `www/tools/roundtrip-mesh-model.mts:43` compara strings `toFixed(5)` de valores
  com ruído float32 antes/depois do arredondamento a 1 µm: 32% "fora" na 2CV, 28% na
  2831A09, idêntico no commit anterior. Real: 65 de 16.488 vértices sem par exato (0,4%),
  triângulos preservados. Comparar por vizinho a ≤ 2 µm.

## Importantes — `www/`

- **I10.** Sem `@UseGuards`: `PUT /geometrias/:id`, `POST …/restaurar`
  (`geometrias.controller.ts:72,110`), `PATCH /produtos/:id` (`produtos.controller.ts:52`),
  `PATCH /catalogos/:id` (`catalogos.controller.ts:77`), `cad/*`, `step/*`, `exportar/aq`.
  Body até 300 MB (`main.ts:14,21-22`) com `validateGeoBuffers` síncrono sobre até 15 M
  números; upload 1 GB em `os.tmpdir()` (`step.controller.ts:35-40`); `python3` por até
  30 min sem limite de concorrência (Revit = 3,6 GB RSS por processo). Guard ou
  `EDICAO_ABERTA=1` explícito; `JSON_BODY_LIMIT` ~50 MB; semáforo de 1 nas conversões.
- **I11.** `step.service.ts:207` (`.catch(() => {})`) e `importacoes.service.ts:90` em
  memória. Restart deixa `BimImport` em `recebido/parseando/gravando` para sempre e a
  página em "Convertendo…"; multer não limpa o tmp. No `onModuleInit`, marcar `falhou` os
  não terminais com `updatedAt` > 1 h.
- **I12.** `@nestjs/mongoose@12.0.0` exige Nest ^11||^12; instalado `10.4.22`. `mongodb@6`
  só em `health.controller.ts:2`; `mongoose@9.9.4` traz `mongodb ~7.5`. Health via
  `@InjectConnection()`; alinhar Nest.
- **I14.** `geometrias.controller.ts:72-108` não chama `spawnThumbWorker`. Confirmado: 4CV
  (`fa9806df`) com `geoEditadoEm` e thumb do import.
- **I15.** `importacoes.service.ts:306-320` ignora `type:'error'` do thumb-worker;
  `:270-275` só rejeita em exit ≠ 0 (exit 0 sem mensagem prende a promise até o timeout de
  5 min); `step.service.ts:258,271,287` pode deixar JSON órfão se falhar entre `store.put`
  e `productModel.create`.
- **I16.** Zero `ValidationPipe`/`class-validator`. `produtos.controller.ts:76` transforma
  objeto em `"[object Object]"`; `curva` e `partes` sem limite; `info.specs` livre ao
  Python.
- **I17.** `http://localhost:4000` fixo em `app/[empresa]/[catalogo]/page.tsx:5`,
  `app/empresa/importar/page.tsx:115`, `app/empresa/page.tsx:66` (ignora `lib/api.ts`);
  `main.ts:42` `listen(4000)` sem `PORT`; `STORAGE_PATH` com defaults distintos em
  `disk-geometry-store.ts:9` e `empresas.controller.ts:34`.
- **Divergências rota × `www/README.md`:** falta `GET /auth/me` (com guard); `GET /logos/:id`
  marcado Bearer mas público (`empresas.controller.ts:96`); `storage/bim/geometrias/`
  vazio e não documentado.

## Importantes — repositório, ambiente e infra

- **I18.** `package-lock.json` e `pnpm-lock.yaml` versionados na raiz; `node_modules/`
  com `.modules.yaml` e `.package-lock.json`. README/CLAUDE dizem `npm install`; `www/` é
  pnpm. Escolher pnpm, apagar `package-lock.json`.
- **I19.** Sem `.nvmrc`, `.python-version`, `packageManager`, `engines`. Máquina: Node
  24.18 (nvm), `/usr/bin/node` 18.19, pnpm 11.24, Python 3.12.3. `build.py:655-668` procura
  Node ≥ 20 em `~/.nvm` para compensar.
- **I20.** Sem `.github/`, LICENSE, `.editorconfig`, `.gitattributes` (`*.aq binary`).
  Testes existem e nada os roda.
- **I21.** `git count-objects` → 6.867 soltos, 0 packs, 134 MB. `gc` só depois de decidir C6.
- **Ambiente não declarado como pré-requisito:** Atlas IP allowlist (só como armadilha,
  em 5 lugares); `mongosh`/`mongod` ausentes apesar de "um `mongodb://127.0.0.1` serve";
  libs do Chromium via apt (README ainda ensina `~/.local/chromium-libs`, que não existe).
  Setup pós-clone espalhado em 4 lugares sem `bootstrap.sh`.
- **Segredos:** nada exposto. `mongodb+srv://` só em `www/.env.example` com placeholder em
  todas as revisões; `.env`/`config.json` nunca entraram no git.

## Importantes — documentação

- **I22.** CLAUDE.md: 2.797 linhas / 160 KB / 69 revisões (5,1 MB de histórico).
  Histórico de sessões = 1.138 linhas (41%), fora de ordem cronológica. Sete notas
  "versões antigas deste arquivo diziam…" (124, 209, 1266, 1607, 1741, 1814, 1950).
  Duplicações: Atlas (4 lugares), sudo/dois Node (3), `page.evaluate` (3), cp1252 (3, uma
  contradizendo), instâncias repetidas (3), POC de edição (5).
- **I23. Afirmações quebradas** (além de C8–C10):

  | Onde | Diz | Real |
  |---|---|---|
  | `CLAUDE.md:1559` | "Bug aberto do OQ3D — ver 'instâncias repetidas não emitem geometria'" | resolvido em 08-30; seção chama-se "…RESOLVIDO" |
  | `CLAUDE.md:215-216` | "`output/` está vazia… 10 catálogos de `input/`" | `output/` tem 16 catálogos, 46 entradas; `input/` tem 16 `.aq` |
  | `CLAUDE.md:760` | ZIP em `output/<slug>-<ts>.zip` | `output/<origem>/<slug>-<ts>.zip` |
  | `CLAUDE.md:1463-1489` | "Integração bilds.com — fase 2 não implementada… o ZIP será consumido" | em produção desde PR #1244 |
  | `CLAUDE.md:1547` | "vazia nas **três** bibliotecas" | 1394/1571 dizem 12; contagens 3/9/10/12/15 pelo arquivo |
  | `CLAUDE.md:415` | `NEXT_PUBLIC_API_URL` configura o web | `[catalogo]/page.tsx:5` hardcoded |
  | `CLAUDE.md:380,388` | `catalogos.controller.ts:31`, `:22` | linhas 25 e 35-36 — refs a linha envelhecem |
  | `CLAUDE.md:2181` | "`--interactive`" | flag aceita e ignorada (`build.py:1537`) |
  | `CLAUDE.md:150` | "869 com `geoUrl`/`thumbUrl`" (Mongo) | Mongo guarda `geoKey`/`thumbKey` |
  | `eng-reversa/README.md:110` | `cd /home/foltz/bilds-bim-3d` | caminho da máquina em comando |
  | `CLAUDE.md:32-55` | tabela "onde está cada conhecimento" | omite `docs/saida-bilds-com/` (2.039 linhas), `docs/plans/`, `www/README.md` |

- **I24.** Skills: `pagina-biblioteca` 1.1.0→1.5.0 nunca citada no CLAUDE.md; `readPixels`
  e `object-fit` só na skill; deflexão do STEP e `GetColor` só na skill `leitor-step`;
  `n_raizes_declarado`/`OQ3DAvisoParse` só no CLAUDE.md. Regra "bump da skill no mesmo
  commit" (`CLAUDE.md:90-91`) não foi cumprida em nenhum dos 20 commits auditados — a
  prática é o commit `docs:` seguinte; a regra em 14-19 até implica isso. Commit `ba8ecf4`
  (`feat(preview): WebPs pré-gerados`) sem entrada no histórico. S5.3 referenciada
  (`1911-1935`) sem arquivo em `docs/sessoes/`. Sessões de 08-23 a 08-28 só no CLAUDE.md.
- **I25.** `docs/plano-produto-dinamico.md`: cabeçalho "nenhuma linha de código escrita";
  §11 para em S4.4 (faltam S5.1, S5.2, S6.1); §13 "lista viva" com linha em branco
  quebrando a tabela (l.785). Não marcado histórico, ao contrário do `plano-integracao`.
- **CONCEPTS.md:** definidos e quase não usados: "Geometry Pointer", "Caminho exato",
  "Forma representativa". Usados e não definidos: OQ3D (46 arquivos), ADR (40), importId
  (44), slug (39), dedup (36), series-rows/catalog-grid, bocal, customUrl, SwiftShader,
  harness, TQi3DReusedObject, Q-H. Idioma misto.

---

## Limpeza

- **L1.** `build.py`: import duplo de `read_aq.extract` (`:74`, `:326`); `_potencia_de`
  duplicada (`:259-264`, `:307-312`); ramo inalcançável `:1199-1201`; `--interactive`
  ignorado; `--skip-ifc` oculto. `build_preview:550-552` copia `vendor/` só se não existe
  (atualizar Three.js nunca propaga).
- **L2.** `ifc_to_geo.py:69` `.replace` no-op; `:82-83` `except: pass`. `parse_ifc.py`
  `:348` engole `create_shape`; `:563` `n_tris` sem uso; cor de material lida de duas
  formas diferentes (`parse_ifc.py:355-364` vs `ifc_to_geo.py:107-123`).
- **L3.** Dedup em 4 implementações (`dedup.py`, `ifc_to_geo.py` numpy, `parse-worker.ts`,
  `mesh-model.ts`); `slugify` em 4 cópias; cena Three.js copiada em 3 templates
  (`series-rows`, `catalog-grid`, `thumbs/harness.html`) — extrair `templates/shared/viewer.js`.
- **L4.** Legado: `www/workers/aq-parser/` (Flask, substituído pelo `parse-worker.ts`),
  `tools/test-worker.ts`, `tools/test-port-s2-2.ts`, `storage/bim/geometrias/`;
  `eng-reversa/tools/{pdf_coords,pdf_akato,aq_referencia,oq3d_anatomy}.py` e `dados/akato-*`
  são estudo arquivável.
- **L5.** `thumbs.mjs:7` documenta `concurrency` não lido. `read_aq.extract` filtra
  `ATIVO=1` mas `peek_metadata` conta `COUNT(*)`.
- **L6.** `www/`: sem lint nem testes unitários; `any` 36× na API (`strictNullChecks:
  false`), 13× no web; `console.log` em `main.ts:30,50`; funções de 258 (`adicionarPrimitiva`),
  183 (`useEffect` do viewport), 163 (`exportIfc`) linhas; exports sem uso em `mesh-model.ts`;
  `@types/jsonwebtoken` em `dependencies`.
- **L7.** `.env.example:45-46` descreve `WORKER_PORT` como do thumb-rasterizer (é do worker
  legado); `WEB_URL` e `PORT` não documentados; `BILDS_NODE` não está em
  `config.example.json`.
- **L8.** `output/preview/index.html` é o único arquivo manual dentro de um diretório de
  build — mover para `templates/` e copiar no build.
- **L9.** `docs/plano-integracao-bilds.md` tem dois "## 9.". `docs/sessoes/TEMPLATE.md`
  não prevê sessões fora do plano; S7.1/S7.2 sem SHA em `Commits:`.
- **L10.** `e2e-editor.mjs:142-146` engole exit ≠ 0 do `validar_aq.py`.
- **L11.** Versões desatualizadas sem urgência: Next 15.5 → 16, Nest 10 → 12, TS 5.9 → 7.
- **L12.** Footprint local: `input/` 2,0 GB, `output/` 2,9 GB, `www/node_modules` 457 MB,
  `www/storage` 118 MB — anotar no README (~5 GB para reproduzir o preview).
- **L13.** `resíduo` desta auditoria no Mongo: import `dd393c56` "auditoria-e2e".
- **L14.** `MEMORY` do agente nesta máquina: OCP em `~/.local`; sem nada que o repo não tenha.

---

## Ordem sugerida para "passar a limpo"

1. ✅ **Hoje, 5 minutos, sem risco:** `git push -u origin poc-edicao` (C5) — feito na S7.5, junto com C6.
2. **Geração acusa erro** (o critério do usuário): ~~C1, C2, C3~~ (S7.4), ~~I1, I2, I3~~ e a
   ~~suíte `tests/` de I9~~ (S7.6) — **faltam I7 e I8**. Um commit por item, cada um
   com a linha correspondente no CLAUDE.md e na skill, e o teste em `tests/`.
3. **Build e testes voltam a ser verdes:** C4, I13; depois um workflow mínimo (I20) que
   rode `py_compile`, `pytest`, `pnpm -r build`, `testes-editor.sh`.
4. **Documentação passa a limpo:** corrigir C8, C9, C10, I23 primeiro (são erros ativos);
   depois a reestruturação de I22 — CLAUDE.md vira mapa de ~400 linhas; histórico vai para
   `docs/sessoes/` (criar S5.3 e as sessões de 08-23…28); conhecimento de formato para
   `docs/conhecimento/` ou para as skills como fonte única; POC de edição para
   `www/README.md`; `plano-produto-dinamico.md` marcado histórico com §13 extraído.
5. **Ambiente declarado:** I5, I18, I19, `bootstrap.sh`, seção única "Pré-requisitos"
   com "como verificar" (`node -v`, `python3 -c 'import OCP'`, Atlas allowlist como passo 0).
6. **Decisões que são do usuário:** ~~C6~~ (decidido e feito na S7.5), C7 (estratégia de
   deploy do preview), I10 (auth na POC ou aceitar só localhost), I6 (matar ou arquivar o
   modo `--ifc`), I4 (promover o writer de `.aq` para `scripts/`).
7. **Limpeza** (L1–L14) conforme cada área for tocada, nunca em commit separado gigante.
