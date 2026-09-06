# Arquitetura — contextos desacoplados sobre uma biblioteca comum

> Fonte de verdade da arquitetura, implementada em 2026-09-06. Cada decisão numerada mora em
> `docs/decisoes/`. Enquanto viver neste repositório, o sistema é POC: **sem auth, sem admin**; a empresa é um
> agrupador de catálogos, não um controle de acesso (ADR-007).

## 1. A ideia em um parágrafo

Um **parser de bibliotecas do AltoQi Builder, em Python, é a biblioteca comum**: destrincha o `.aq`,
extrai geometria, gera miniaturas, escreve `.aq` e o ZIP da bilds.com, converte STEP/IGES/IFC e lê
catálogos de plugins web. É **stateless**: arquivo entra, arquivo ou JSON sai; não conhece Mongo,
HTTP nem caminhos do repositório. Em volta dela, **um serviço por contexto de negócio** —
criador de catálogos, API de catálogo, editor de peças, gerador de ZIP, conversores — cada um um
deployable próprio, consumindo a biblioteca e os pacotes comuns. Na POC tudo sobe na mesma máquina
com um comando; a separação existe para que cada contexto possa ser portado para outro sistema
levando só o que é seu (seção 4).

## 2. Camadas

```
bilds-bim-3d/
├── biblioteca/                       ← A BIBLIOTECA COMUM (Python, pacote `bim_pipeline`) — stateless, sem Mongo
│   ├── bim_pipeline/
│   │   ├── aq/            leitura (read_aq, oq3d) e escrita (aq_writer, oq3d_writer, schema-aq-607.sql)
│   │   ├── geometria/     contrato {pos,col,idx}, dedup (único), eixos (único lugar das conversões), bocais
│   │   ├── catalogo/      catalogo (build_catalog_from_aq), inferencia, slugify (único), diag; fontes/: aq, plugin_catalogo_web
│   │   ├── conversores/   step_iges, ifc (ifc_to_geo + parse_ifc), rfa_partatom
│   │   ├── miniaturas/    miniaturas.py, thumbs.mjs, harness.html, package.json (playwright + three)
│   │   ├── saida/         zip_bilds (ÚNICO escritor do ZIP), geo_to_aq (uma peça), catalogo_to_aq (catálogo)
│   │   ├── processo.py    vigiar_stdin
│   │   ├── cli/           um módulo por CLI + ferramentas/ (oq3d_anatomy, aq_referencia, validar_aq, oq3d_roundtrip)
│   │   └── contratos/     JSON Schema dos contratos biblioteca ↔ serviços (a biblioteca os define; @bim/base valida o que lê)
│   ├── pyproject.toml     `pip install -e biblioteca[cad,dev]`
│   └── README.md
├── pacotes/                          ← compartilhado entre os serviços Nest (TypeScript, compilado para dist/)
│   ├── base/              processo.ts, BibliotecaCli (roda `python -m bim_pipeline.cli.*`), upload, validação, health, download em stream
│   └── dominio/           schemas Mongoose, IGeometryStore + Disk, storage-path, geo-buffers, asset-cache, remoção em cascata, MongoProntoGuard
├── servicos/                         ← UM DEPLOYABLE POR CONTEXTO (Nest; main.ts, porta, .env, README próprios)
│   ├── criador-de-catalogos/  :4100  importações (.aq/.zip, plugin web), fila, recuperação no boot, publicação (GRAVA Mongo + storage),
│   │                                 miniaturas (import e regerar), exportar catálogo salvo → .aq, DELETE importação. Usa base + dominio + biblioteca.
│   ├── catalogo-api/          :4000  leitura: empresas (+criar, logo via IGeometryStore), catálogos, produtos, geometrias GET, thumbs GET,
│   │                                 remoção em cascata. Usa base + dominio. Sem Python, sem Chromium.
│   ├── editor-de-pecas/       :4400  PATCH produto (infoOriginal), PUT geometria (copy-on-write, .orig), restaurar, pedir miniatura ao criador.
│   │                                 Usa base + dominio.
│   ├── gerador-zip/           :4200  POST /zip (.aq|.zip → ZIP bilds.com em stream). STATELESS: sem Mongo, sem storage, sem dominio.
│   └── conversores/           :4300  POST /tesselar (STEP/IGES/IFC → geometria), POST /aq (geometria → .aq de uma peça),
│                                     POST /plugin/inspecionar (DLL → host/categorias). STATELESS.
├── web/                              ← Next :3000, um app, árvore por contexto e UM cliente por serviço em src/servicos/
├── tests/                            ← biblioteca/, servicos/ (harnesses), arquitetura/ (guardas), fixtures por papel (não por empresa)
├── docs/                             ← conhecimento/ (formatos, algoritmos, padrões — sem empresas), decisoes/, integracoes/, historico/ (não carregar)
├── input/ (gitignored) · storage/ (gitignored) · .github/workflows/ci.yml
└── CLAUDE.md (mapa) · README.md (subir tudo) · CONCEPTS.md
```

## 3. Regras de fronteira (cada uma é um teste em `tests/arquitetura/`)

1. **Biblioteca** não importa nada de fora de `bim_pipeline`, não conhece Mongo, HTTP nem caminhos do repositório; toda entrada e saída é arquivo/JSON; toda CLI aceita `--sair-com-stdin` (ADR-011).
2. **Serviços só chegam ao Python por `pacotes/base` (`BibliotecaCli`)** — um só lugar sabe `PYTHON`, `BIBLIOTECA_DIR` e os nomes das CLIs. Nenhum `child_process` fora de `pacotes/base`.
3. **Stateless de verdade**: `gerador-zip` e `conversores` não importam `pacotes/dominio`, não têm `MongooseModule`, não leem `STORAGE_PATH`; o `/health` deles só confere a biblioteca (ADR-012, ADR-013).
4. **Dados**: só `criador-de-catalogos`, `catalogo-api` e `editor-de-pecas` importam `dominio`. Quem grava o quê está na seção 5. Mongo e storage compartilhados são **acoplamento aceito e documentado da POC**; `IGeometryStore` e os schemas são a costura de porte (ADR-004, ADR-014).
5. **Web**: um cliente por serviço em `web/src/servicos/`; nenhuma URL fixa fora deles; componente de um contexto não importa cliente de outro (o editor usa `editor` + `conversores`; a home usa `catalogo` + `zip`; importar usa `criador` + `catalogo`).
6. **Sem empresas**: nomes de fabricante, domínios e caminhos efêmeros da POC (lista em `tests/arquitetura/termos_efemeros.txt`) não aparecem em `biblioteca/`, `servicos/`, `pacotes/`, `web/`, `tests/`, `docs/conhecimento/` e `docs/skills/`; só em `docs/historico/`, `docs/integracoes/` e `tests/fixtures.local.*` (ADR-016).
7. **Contratos** entre biblioteca e serviços têm JSON Schema em `biblioteca/bim_pipeline/contratos/` — a biblioteca os define porque é quem emite; ela prova em teste que emite conforme (`tests/arquitetura/test_contratos.py`) e `@bim/base` valida o que lê (`validarContrato`, ajv) (ADR-015).

## 4. O que cada contexto leva consigo ao ser portado

| Contexto | Leva | Depende de |
|---|---|---|
| gerador-zip | `servicos/gerador-zip` + `biblioteca` + `pacotes/base` | nada externo (Chromium para miniaturas; sem ele o ZIP sai sem `thumbs/`) |
| conversores | `servicos/conversores` + `biblioteca` + `pacotes/base` | OCP e ifcopenshell instalados |
| criador-de-catalogos | serviço + `biblioteca` + `base` + `dominio` | Mongo, storage, Chromium |
| editor-de-pecas | serviço + `base` + `dominio` + `web/src/(editor)` | Mongo, storage, criador (miniatura), conversores (tesselar) |
| catalogo-api | serviço + `base` + `dominio` + `web/src/(catalogo)` | Mongo, storage |

## 5. Quem grava o quê

| Coleção / prefixo do storage | Grava | Lê |
|---|---|---|
| `bim_imports` | criador (ciclo `recebido → parseando → gravando → publicado \| vazio \| falhou`) | criador, web (`/importar`) |
| `bim_catalogs` | criador (upsert na publicação, recontagem), catalogo-api (`PATCH` metadados, remoção), editor (recontagem de filtros ao editar série) | todos |
| `bim_products` | criador (`insertMany` na publicação, `thumbKey`), editor (`specs`, `infoOriginal`, `geoKey`, `geoKeyCompartilhada`, `geoEditadoEm`, `thumbErro`), catalogo-api (remoção) | todos |
| `companies` | catalogo-api | todos |
| `geo/<importId>/…` | biblioteca via criador (publicação); editor (copy-on-write, `.orig.json`) | catalogo-api, criador (miniaturas), editor |
| `thumbs/<importId>/…` | criador (import e regerar) | catalogo-api |
| `catallog/<importId>/…` (downloads do plugin web) | criador | criador |
| `logos/…` | catalogo-api (via `IGeometryStore`) | catalogo-api |

Nenhum dado de fabricante fica no repositório: `input/`, `storage/` e as fixtures locais são gitignored.

## 6. Regras de mudança

Um commit por item; o teste que prova o comportamento novo entra no mesmo commit; `python3 -m pytest
-m "not thumbs"` e `pnpm -r build` verdes antes de commitar; a documentação do que mudou vai no mesmo
commit, no documento de origem. Uma decisão nova ou revista é um ADR em `docs/decisoes/`. O plano de
fases que implementou esta arquitetura está arquivado em `docs/historico/planos/`.

## 7. Invariantes

Coleções do Mongo e formato dos ponteiros (`geo/<importId>/…`, `thumbs/<importId>/…`); o contrato do
ZIP consumido pela bilds.com e o `catalog.json` (`docs/conhecimento/zip-bilds-formato.md`); uma
implementação por algoritmo na biblioteca (parser, OQ3D, miniaturas, conversores); sem auth; empresa
por `customUrl`.
