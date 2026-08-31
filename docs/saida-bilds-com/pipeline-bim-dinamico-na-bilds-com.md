# Pipeline BIM dinâmico na bilds.com — corpo de conhecimento para a feature branch

> **Documento único e definitivo.** Reúne o que a POC `bilds-bim-3d` provou, o que já
> existe na `bilds.com` (verificado em código, não em documentação), a arquitetura
> recomendada para o ambiente real (containers na AWS, S3, banco de produção) e as
> armadilhas que não devem ser redescobertas.
>
> **Data:** 2026-08-31 · **Repos lidos:** `bilds-bim-3d` (topo de `main`, commit `79997d0`)
> e `bilds.com` (branch `develop`, commit `7d99f072`).
>
> **Este documento é a entrada para:** um `ce-plan` (planejamento), um `ce-doc-review`
> (revisão do plano), um `ce-work` (implementação) e um `code-review` posterior.

---

## 0. Como usar este documento

### 0.1 Para quem é

Para o agente (ou pessoa) que vai abrir uma **feature branch na `bilds.com`** e
implementar a geração de catálogo BIM a partir do arquivo de biblioteca do fabricante
(`.aq`), com indicação de progresso na interface e todo o pipeline de API que segue ao
upload.

### 0.2 Ordem de leitura recomendada

1. **§1** — o que se quer construir, e o que muda em relação ao fluxo de ZIP atual.
2. **§3** — o terreno da `bilds.com`. Leia inteiro antes de planejar: metade das decisões
   já está tomada pelo que existe.
3. **§4** — o núcleo transferível da POC, com os números medidos.
4. **§5** — a arquitetura recomendada, decisão por decisão, com alternativas.
5. **§7** — armadilhas. Leia antes de escrever a primeira linha.
6. **§8** — incrementos sugeridos, para virar plano.
7. **§10** — o que precisa de decisão humana antes de codar.

### 0.3 Regras de uso

- **Onde este documento diverge de um `.md` da `bilds.com`, este documento está certo** —
  ele foi conferido contra o código em 2026-08-31. As divergências conhecidas estão
  catalogadas em **§3.2**; corrija a documentação lá quando implementar.
- **Nada aqui substitui a leitura de `bilds.com/CLAUDE.md`.** As convenções obrigatórias
  da casa (i18n, `EnvService`, DTO + Zod, soft delete, Swagger) reprovam em review e estão
  resumidas em §3.8, não repetidas por extenso.
- **Nenhum caminho de arquivo deste documento é presumido.** Todos foram abertos. Ainda
  assim, confira a existência antes de recomendar: `develop` se move.
- Caminhos prefixados com `bilds.com/` são do repositório de produção; prefixados com
  `bilds-bim-3d/` são da POC (outro repositório, não disponível no runtime da bilds.com).

### 0.4 O que este documento NÃO faz

- Não decide o modelo de execução do trabalho pesado (fork no pod da API × worker
  dedicado). Apresenta as opções com custo e recomenda uma — a decisão é do tech-lead
  (§10, decisão **D-2**).
- Não escreve o plano. Deliberadamente: o plano é o próximo passo, e sai melhor com
  este material na mão do que embutido nele.
- Não trata do pipeline estático (`scripts/build.py` da POC, geração de ZIP). Aquilo
  continua existindo e não é afetado.

---

## 1. O que se quer construir

### 1.1 O fluxo de hoje na bilds.com

```
[fora da plataforma]                      [bilds.com]
pipeline local bilds-bim-3d
  .aq → parse → geo/*.json + thumbs/*.webp
      → catalog.json + manifest.json
      → ZIP
                    │
                    ▼  upload manual, admin do backoffice
        POST /companies/:id/b-bim-3d  (multipart, campo "zip")
                    │
                    ▼
        BimCatalogService.uploadCatalog()
          AdmZip extrai → S3 (ou disco em dev) → upsert em bim_catalogs
                    │
                    ▼
        página pública /{customLink}/{catalogSlug}
          lê catalog.json inteiro do storage; produtos vêm do JSON
```

Consequências do modelo atual, todas reais:

- **Só um admin Bilds publica**, e só depois que alguém rodou o pipeline numa máquina
  local com Python, Chromium e as bibliotecas `.aq` em disco.
- **O fabricante não tem autonomia.** Ele já sobe `.rvt`/`.dwg`/`.ifc`/`.zip` como
  arquivo de biblioteca (`Company.libraryFiles`), mas isso é só um download — não gera
  catálogo 3D.
- **Não há busca nem filtro server-side.** O `catalog.json` é baixado inteiro pelo
  browser (856 produtos no caso da Amanco).
- **Atualizar um produto é regerar tudo e re-subir o ZIP.**

### 1.2 O fluxo que se quer

```
[bilds.com — fabricante ou admin]
  MediaUploader (componente que já existe)
      │  arquivo .aq, progresso real de upload via XHR
      ▼
  upload autenticado → S3 (objeto bruto)
      │
      ▼
  POST .../bim-imports  → cria documento de importação, enfileira
      │                    devolve { importId, status }
      ▼
  worker: baixa o .aq → parseia (TypeScript) → dedup de vértices
      → geometria para o S3 (uma chave por geometria)
      → produtos para o MongoDB (bim_products)
      → catálogo em bim_catalogs
      → miniaturas (Three.js real, headless) para o S3
      │
      ▼  a interface faz polling de GET .../bim-imports/:importId
  UI: passo a passo + contadores (produtos parseados, miniaturas geradas)
      │
      ▼
  página pública /{customLink}/{catalogSlug}
      produtos vindos do banco (paginação/filtro possíveis)
      miniatura pronta do CDN; geometria só quando o modal 3D abre
```

### 1.3 Escopo

**Dentro:**

| Item | Observação |
|---|---|
| Reuso do `MediaUploader` para o `.aq` | Componente inalterado na essência; ver §5.2 para o único ponto aditivo |
| Endpoint autenticado de upload do `.aq` | Com `diskStorage`, não `memoryStorage` (§7, A-14) |
| Documento e máquina de estados de importação | Com contadores para a barra de progresso |
| Pipeline: parse → geometria → produtos → catálogo | Núcleo portado da POC (§4) |
| Miniaturas server-side idênticas ao viewer | ADR-004 da POC; ver §5.4 para o custo em container |
| `S3GeometryStore` | Mesma interface do `DiskGeometryStore`, com `stat()` |
| Progresso na UI | Polling via RTK Query; passos + percentual |
| Página pública consumindo do banco | Coexistindo com os catálogos ZIP já publicados |
| Visibilidade/publicação do catálogo | Requisito, não hardening — §5.7 |
| Autorização, rate limit, i18n, testes | Convenções da casa (§3.8) |

**Fora:**

| Item | Por quê |
|---|---|
| Caminho IFC (`parse_ifc.py`) | O `.aq` já traz a mesma geometria; o IFC serve como gabarito de validação, não como entrada |
| Aposentar o upload de ZIP | Os 9 catálogos publicados continuam funcionando; a remoção é decisão posterior |
| Pipeline estático da POC | Continua no outro repositório, sem mudança |
| Editor de catálogo (renomear produto, reordenar) | Não é necessário para o primeiro incremento |
| Curva Q-H nova / novos layouts | O que existe (`series-rows`, `catalog-grid`) atende |

---

## 2. Vocabulário e mapa de nomes

A POC nasceu com nomes em português; a `bilds.com` padroniza campos de banco em inglês
(a renomeação PT→EN aconteceu em 2026-08-17). **A tradução tem que ser feita, e é uma
fonte real de bug.**

### 2.1 Módulos e rotas

| POC (`bilds-bim-3d/www`) | bilds.com |
|---|---|
| `importacoes/` | `bim-imports/` (submódulo de `b-bim-3d/`) |
| `catalogos/` | `b-bim-3d/` (controller público já existente) |
| `empresas/` | `companies/` (já existe, em produção) |
| `geometrias/` | rota de geometria — hoje há proxy em `b-bim-3d/:customLink/:slug/geo/:filename` |
| `thumbs/` | miniatura servida direto do CloudFront (`thumbBaseUrl`) |
| `Company.customUrl` | `Company.customLink` |
| `Company.ownerId` | `Company.createdBy.id` (id de **profile**) + `Company.administrators[].id` |

### 2.2 Campos de produto

Três grafias convivem hoje. Não confunda:

| Conceito | `bim_products` da POC | `catalog.json` (contrato do ZIP) | Recomendado na bilds.com |
|---|---|---|---|
| nome | `nome` | `nome` | `name` |
| série/família | `serie` | `serie` | `series` |
| especificações | `specs` | `specs` | `specs` |
| curva Q-H | `curva` | `curva` | `curve` |
| potência | `potencia` | — | `power` |
| chave da geometria | `geoKey` | `geo` (nome de arquivo) | `geoKey` |
| chave da miniatura | `thumbKey` | `thumb` (nome de arquivo) | `thumbKey` |

> **Armadilha real, já cometida:** o frontend da `bilds.com` (`components/b-bim-3d/types.ts`)
> consome `BimCatalogData` com campos **em português** (`titulo`, `fabricante`, `filtros`,
> `produtos`), porque esse é o formato do `catalog.json`. O documento MongoDB
> `bim_catalogs` usa **inglês** (`title`, `manufacturer`, `filters`). O bug B-15 do módulo
> foi exatamente isso: a interface do admin ficou com nomes PT e os cards apareceram
> vazios. Ao servir produtos do banco, decida o formato da resposta **uma vez** e
> documente; a função `resolveFields()` que existe para retrocompatibilidade é o
> precedente de como lidar com documentos antigos.

### 2.3 Termos do domínio do arquivo

| Termo | O que é |
|---|---|
| `.aq` | Biblioteca BIM do AltoQi Builder. SQLite direto **ou** ZIP contendo um SQLite. 153 MB (Dancor) a 618 MB (Maxbar) |
| OQ3D | Formato binário da geometria 3D, no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`. Assinatura ASCII `OQ3D 3D Objects File` |
| peça | Variante de produto (tabela `PECA`) |
| grupo de peça | Série/família (tabela `GRUPO_PECA`, `NOME_GP`) |
| simbologia 3D | A malha (tabela `SIMBOLOGIA_3D`). **Várias peças compartilham a mesma malha** |
| classe de simbologia | `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE`, padrão `"FABRICANTE - Linha"` — a fonte confiável do nome do fabricante |
| geo JSON | `{ pos, col, idx }` — arrays flat prontos para `THREE.BufferGeometry`, em **metros, Y-up** |
| import | Uma execução do pipeline sobre um arquivo. Tem id, estado e produtos vinculados |

---

## 3. O terreno: o que já existe na bilds.com

Tudo nesta seção foi lido no código em 2026-08-31, em `develop` (`7d99f072`).

### 3.1 O módulo `b-bim-3d` hoje

```
bilds.com/apps/api/src/b-bim-3d/
├── constants.ts                          — LOCAL_BASE_DIR, THUMB_MAX_BYTES, THUMB_EXTENSIONS
├── b-bim-3d.module.ts
├── schemas/bim-catalog.schema.ts          — coleção bim_catalogs
├── repositories/bim-catalog.repository.ts
├── services/bim-catalog.service.ts        — 438 linhas, uploadCatalog() é o grosso
├── controllers/bim-catalog.controller.ts  — 206 linhas, 9 rotas
└── dtos/{upload-bim-catalog,update-layout}.dto.ts
```

Especificações e testes existentes: `services/bim-catalog.service.spec.ts` (598 linhas),
`controllers/bim-catalog.controller.spec.ts`, `repositories/bim-catalog.repository.spec.ts`.

**As 9 rotas, com auth:**

| Método | Rota | Auth |
|---|---|---|
| POST | `companies/:id/b-bim-3d` | `@VerifySession()` + `assertPermission` |
| GET | `companies/:id/b-bim-3d` | `@VerifySession()` + `assertPermission` |
| PATCH | `companies/:id/b-bim-3d/:slug` | `@VerifySession()` + `assertPermission` |
| DELETE | `companies/:id/b-bim-3d/:slug` | `@VerifySession()` + `assertPermission` |
| GET | `b-bim-3d/summary` | `@VerifySession({ roles: ['Admin'] })` |
| GET | `b-bim-3d/files/*path` | `@PublicAccess()` (só serve em modo local) |
| GET | `b-bim-3d/:customLink/:slug/geo/:filename` | `@PublicAccess()` (proxy anti-CORS) |
| GET | `b-bim-3d/:customLink/:slug/catalog` | `@PublicAccess()` (proxy anti-CORS) |
| GET | `b-bim-3d/:customLink/:slug` | `@PublicAccess()` |

> **KTD-3 continua válido e é ordem de declaração, não de configuração:** `summary`,
> `files`, `/geo/:filename` e `/catalog` **devem** ser declarados **antes** de
> `/:customLink/:slug`. O NestJS registra na ordem do arquivo; um segmento fixo depois do
> dinâmico faz `"summary"` ser lido como `customLink`. Silencioso, compila.
> **Toda rota nova em `b-bim-3d/...` cai nessa mesma armadilha.**

**Schema `bim_catalogs`** (`schemas/bim-catalog.schema.ts`) — o ponto importante para o
trabalho novo:

```typescript
@Prop({ type: String, required: true }) catalogUrl: string    // ← required
@Prop({ type: String, required: true }) geoBaseUrl: string    // ← required
@Prop({ type: String, default: null })  thumbBaseUrl?: string
```

`_id` é `uuidv4` (String, não ObjectId). Índices: `{ companyId, slug }` único e
`{ companyCustomLink, slug }`. `deletedAt` existe mas é **sempre `null`** — catálogo usa
**hard delete** (KTD-5, aprovado pelo tech-lead).

> **Conflito a resolver:** `catalogUrl` e `geoBaseUrl` são obrigatórios porque hoje todo
> catálogo veio de um ZIP e aponta para arquivos no storage. Um catálogo gerado do `.aq`
> **não tem `catalog.json`** — os produtos estão no banco. Ver §5.6.

**`assertPermission` (`services/bim-catalog.service.ts`)** é o padrão de autorização a
reusar tal como está:

```typescript
const company = await this.companyModel.findOne({ _id: companyId, deletedAt: null }).lean()
if (!company) throw new NotFoundException('Empresa não encontrada')
const { roles } = await getRolesForUser('public', userId)   // 'public' = tenant default do SuperTokens
if (roles.includes('Admin')) return company                 // KTD-10: admin Bilds bypassa
const profile = await this.profileRepository.findByIdAuth(userId)
const profileId = profile._id.toString()
const isCreator = company.createdBy?.id === profileId
const isAdmin = (company.administrators ?? []).some((a) => a.id === profileId)
if (!isCreator && !isAdmin) throw new ForbiddenException(...)
```

Note: **o id comparado é o do `Profile`, não o `userId` do SuperTokens.** O caminho é
`userId (idAuth) → ProfilesRepository.findByIdAuth → profile._id`.

**Storage condicional:** o service faz, no construtor,
`this.localStorage = this.envService.get('BIM_STORAGE') === 'local'`. Em modo local grava
em `apps/api/public/b-bim-3d/{companyCustomLink}/{slug}/` e monta URLs
`http://localhost:{API_SERVER_PORT}/b-bim-3d/files/...`; em modo S3 grava em
`b-bim-3d/{companyCustomLink}/{slug}/` e monta URLs com `AWS_CLOUD_FRONT_BASE_URL`.

**Validações do upload já implementadas** (reaproveitar a lista, adaptando ao `.aq`):
máx. 10.000 entradas de ZIP; soma de tamanhos declarados ≤ 500 MB; slug
`^[a-z0-9][a-z0-9\-_]{0,60}$`; layout em enum; geo ≤ 10 MB por arquivo; thumb ≤ 2 MB;
`path.basename()` em toda chave de S3; containment check em `serveLocalFile`; filtro de
MIME/extensão no `FileInterceptor`; `fileSize: 100 MB` no Multer; rollback de storage e
de banco em `try/catch`.

### 3.2 Correções ao `docs/modules/bim-3d-module.md`

O documento do módulo (881 linhas) é excelente e **tem três afirmações que o código já não
sustenta**. Um agente que confiar nelas vai procurar código que não existe:

| O que o doc diz | O que o código diz |
|---|---|
| **KTD-2:** `constants.ts` exporta `LOCAL_STORAGE = !process.env.AWS_ACCESS_KEY_ID \|\| process.env.BIM_STORAGE === 'local'` | Não existe `LOCAL_STORAGE` em lugar nenhum de `apps/api/src`. O `constants.ts` exporta só `LOCAL_BASE_DIR`, `THUMB_MAX_BYTES` e `THUMB_EXTENSIONS`. A flag é derivada no service, de `BIM_STORAGE` apenas — `AWS_ACCESS_KEY_ID` não participa (e nem existe no schema de env: está comentada em `config/env/env.ts:48`) |
| **KTD-4:** `serveLocalFile` aplica allowlist de CORS via `CORS_ALLOWED_ORIGINS` | `serveLocalFile` **não escreve nenhum header de CORS**. A var `CORS_ALLOWED_ORIGINS` não existe no `env.ts` nem em `apps/api/src`. O que existe é o CORS global em `main.ts` (por `FRONTEND_URL`/`ADMIN_URL`/`SUPERTOKENS_API_DOMAIN`) |
| **Tabela de env vars** lista `AWS_ACCESS_KEY_ID` e `CORS_ALLOWED_ORIGINS` | Nenhuma das duas está declarada. Credencial de AWS vem do `defaultProvider` do SDK (IRSA/role do nó no EKS); em `NODE_ENV=local` vem do profile `AWS_PROFILE_S3` |

Correção adicional, em `apps/api/src/files/controllers/files.controller.ts`:

- Um comentário no `uploadFile` afirma "Dedicated, more restrictive throttle for this
  endpoint: 10 req/60s per IP". **Não há `@Throttle` nesse handler.** O único throttler é
  o global `default` (100 req/60 s, `config/throttler.options.ts`), ligado por
  `SECURITY_RATE_LIMIT_ENABLED` (default `true`).
- O `@ApiOperation` diz "max 500MB"; o validador é
  `new MaxFileSizeValidator({ maxSize: 1024 * 1024 * 1024 })` — **1 GB**.

> Ao implementar, atualize `docs/modules/bim-3d-module.md` com estas correções **no mesmo
> PR**. É a regra "documentação primeiro" das duas casas, e o próximo agente vai ler o doc,
> não o código.

### 3.3 O componente de upload que existe

Este é o ponto de partida pedido: reusar o que já existe e acrescentar progresso.

**`bilds.com/apps/web/src/components/UploadFile/MediaUploader.tsx`** (1.167 linhas,
`'use client'`).

Props relevantes (interface `MediaUploaderProps`, linha 441):

| Prop | Tipo | Para quê |
|---|---|---|
| `acceptType` | `string` | Categorias separadas por vírgula: `"image"`, `"video"`, `"file"`, `"link"`. **Não existe `allowedTypes`** — erro comum |
| `allowedExtensions` | `string[]` | Opt-in. Restringe a extensões específicas (`['.aq']`). Rejeita **antes** de qualquer upload |
| `onFileRejected` | `(reason: 'size' \| 'extension', fileName: string) => void` | Opt-in. Permite ao consumidor exibir toast traduzido |
| `maxFiles` | `number` | Use `1` |
| `maxMegaBytes` | `number` | Limite por arquivo em MB |
| `moduleType` | `string` | Vai como campo extra no `FormData`, usado para rotear pasta/CDN |
| `value` / `onChange` | `MediaItem[]` | Valor controlado, integra com `react-hook-form` |
| `onUploadComplete` | `(url, media) => void` | Dispara quando **um** upload termina, já com a URL final |
| `onUploadStatusChange` | `(isComplete: boolean) => void` | Dispara quando **todos** terminaram |

**O progresso de upload já existe e é real.** `MediaItem.progress` (0–100) é alimentado
por `xhr.upload.onprogress` em
`bilds.com/apps/web/src/queries/medias.ts` → `uploadMedia`, que usa `queryFn` com
`XMLHttpRequest` (não `fetch`) exatamente para ter progresso. A barra é renderizada na
linha 271 do `MediaUploader`. **Não reimplemente isso.**

Ponto de atenção arquitetural, do próprio `medias.ts`:

```typescript
const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''
xhr.open('POST', `${baseUrl}/files/upload`)      // ← endpoint fixo no código
xhr.send(form)
```

O endpoint é **hardcoded**. Se o `.aq` precisar de outro endpoint (e precisa — ver §5.2),
isso exige uma mudança aditiva de ~6 linhas aqui, no mesmo espírito de como
`allowedExtensions` foi adicionado.

**Precedente de uso com biblioteca BIM** — o formulário do fabricante já faz isso:

```typescript
// apps/web/src/containers/Company/EditCompany/steps/LibrariesAndFiles.tsx:45
const BIM_LIBRARY_EXTENSIONS = ['.rvt', '.dwg', '.ifc', '.zip']
const OTHER_FILE_EXTENSIONS  = ['.pdf', '.docx', '.xlsx', '.zip']
// ...:963
<MediaUploader
  label="" maxFiles={1} acceptType="file" maxMegaBytes={1024}
  allowedExtensions={fileType.bimLibrary ? BIM_LIBRARY_EXTENSIONS : OTHER_FILE_EXTENSIONS}
  onFileRejected={(reason) => { /* toast traduzido */ }}
  moduleType="company-files"
  value={fileMedias} onChange={...} onUploadStatusChange={...}
/>
```

O mesmo arquivo existe duplicado em `CreateCompany/steps/LibrariesAndFiles.tsx` (linhas
45/46 e 977 idênticas). **`.aq` não está em nenhuma das duas listas.**

**O endpoint `POST /files/upload`** (`apps/api/src/files/controllers/files.controller.ts`):

- **É `@PublicAccess()`** — upload anônimo. Registre isso: é o fator decisivo de §5.2.
- Validadores em cadeia: `MaxFileSizeValidator(1 GB)` → `AllowedExtensionValidator` →
  `AllowedContentTypeValidator`.
- `ALLOWED_UPLOAD_EXTENSIONS` (Set no topo do arquivo) inclui `zip`, `rar`, `rvt`, `dwg`,
  `ifc` — **não inclui `aq`**.
- `apps/api/src/files/utils/allowed-content-type.util.ts` traz `EXTENSION_SIGNATURE_RULES`,
  regra de magic bytes por extensão, com `trustExtensionWhenUndetected` para os formatos
  AEC sem assinatura confiável (`ifc` é texto STEP puro; `rvt` compartilha o container OLE
  com `.doc`/`.xls`).
- Usa `FileInterceptor('file')` **sem `storage`** → **memoryStorage**: o arquivo inteiro
  vira `Buffer` em memória do pod.
- `BodyLimitMiddleware` (`config/security/body-limit.middleware.ts`) aplica limites de
  `json`/`urlencoded` por path (`/files`, `/upload` → `SECURITY_BODY_LIMIT_UPLOAD`, default
  `10mb`). **Não afeta multipart** — o multer é que manda ali.
- **CSRF não é obstáculo:** `CSRFGuard` (`config/security/csrf.guard.ts`) só valida quando
  o handler tem `@RequireCSRF()`, e **nenhum handler no projeto usa o decorator**.

**A regra da plataforma sobre upload** (`bilds.com/CLAUDE.md`, seção "Upload de Arquivos"):

> ⚠️ **NUNCA envie arquivos diretamente de um serviço NestJS para o S3.** O backend recebe
> apenas URLs prontas no payload; o upload é responsabilidade exclusiva de
> `POST /files/upload`.

E a exceção já registrada (KTD-9 de `docs/modules/bim-3d-module.md`): o upload de ZIP do
BIM 3D **é** feito de dentro do service, porque o ZIP é um container que precisa ser
extraído server-side. **O `.aq` é o mesmo caso**, e mais forte ainda: nada do que o
usuário mandou é servido diretamente. A arquitetura recomendada em §5.2 respeita a regra
principal (o DTO de importação recebe uma **URL**, não binário) e usa a exceção só no
endpoint de upload.

### 3.4 Empresa, fabricante e portal de fabricantes

**`bilds.com/apps/api/src/companies/schemas/company.schema.ts`** (517 linhas). Campos que
importam:

| Campo | Tipo | Nota |
|---|---|---|
| `_id` | `String` (uuidv4) | Não é ObjectId |
| `customLink` | `String` único (default uuidv4) | **Primeiro segmento da URL pública.** `uploadCatalog` rejeita empresa sem ele |
| `partner` | `boolean?` | Marca fabricante parceiro. Índice `idx_partner`. É o filtro do portal |
| `createdBy` | subdoc com `id` (profile), `name`, `customLink`… | Dono |
| `administrators` | array de subdocs com `id`, `role` | Co-administradores |
| `libraryFiles` | `File[]` (subdoc embutido) | **"Biblioteca BIM" como arquivo para download** |
| `otherFiles` | `File[]` | Acervo técnico |
| `deletedAt` | `Date \| null` | Soft delete padrão |

O subdoc `File` (linha 87) tem `_id` (uuid), `size`, `mimetype`, `createdAt`, `title`,
`softwareType`, `url`, `imageUrl?`, `order`, `category?`, `version?` (formato `MM/YYYY`),
`shortDescription?` (≤200), `includedParts?: string[]`, `totalPieces?: number | null`
(1–9999), `downloadCount` (incrementado em `POST /:id/download-file`).

> **Distinção que precisa ficar clara no plano:** `Company.libraryFiles[]` é o **arquivo**
> que o profissional baixa (`.rvt`, `.ifc`…). `bim_catalogs` é o **catálogo 3D navegável**.
> São coisas diferentes hoje e podem continuar sendo. Uma decisão de produto em aberto
> (§10, **D-6**): ao subir o `.aq` e gerar o catálogo, esse mesmo `.aq` deve aparecer
> também como `libraryFile` para download? Se sim, o link entre os dois precisa existir no
> schema.

**Portal de fabricantes** (`docs/company/manufacturers-portal.md`, 1.020 linhas):
`/portal-de-fabricantes`, container `apps/web/src/containers/Manufacturers/Manufacturers.tsx`,
10 seções. A seção "Bibliotecas BIM" lista `libraryFiles` de empresas `partner: true` via
`BimLibraryCard`; o download passa por URL pré-assinada com cooldown de 5 min no
localStorage; visitante anônimo vê `DownloadLoginModal`. A área de gestão do fabricante é
`apps/web/src/containers/Company/{EditCompany,CreateCompany}/steps/LibrariesAndFiles.tsx` e a
exibição na página da empresa é `containers/Company/sections/CompanyBimSection.tsx` +
`containers/Company/hooks/useCompanyFiles.ts`.

**Onde a nova tela deve morar** — recomendação, não fato: a superfície natural é a mesma
área de gestão do fabricante (`EditCompany`), como um passo/aba "Catálogo 3D" ao lado de
"Bibliotecas e arquivos", e **espelhada no admin** (`apps/admin/src/app/b-bim-3d/[companyId]/`)
para que o admin Bilds continue publicando por qualquer fabricante — o bypass do KTD-10 já
dá a permissão.

### 3.5 Storage: S3, CloudFront, credenciais

**`bilds.com/apps/api/src/common/services/s3.service.ts`** — métodos existentes:

```typescript
uploadBuffer(buffer, key, contentType): Promise<string>   // devolve `${cdnBaseUrl}/${key}`
uploadBase64(base64, fileName): Promise<string>           // key = `${Date.now()}-${fileName}`
uploadFile(file: Express.Multer.File, folderPath = 'uploads/'): Promise<string>
deletePrefix(prefix): Promise<void>                       // ListObjectsV2 paginado + DeleteObjects
getSignedUrl(fileUrl, fileName, expiresIn = 3600): Promise<string>
```

Cliente: `new S3Client(nodeEnv === 'local' ? { region, credentials: defaultProvider({ profile: AWS_PROFILE_S3 }) } : { region })`.
Em produção **não há chave de acesso em env** — a credencial vem da cadeia padrão do SDK
(role do pod/nó no EKS).

Env relevantes (`apps/api/src/config/env/env.ts`, todas via `EnvService`, nunca
`process.env`): `AWS_REGION`, `AWS_S3_BUCKET`, `AWS_CLOUD_FRONT_BASE_URL`,
`AWS_PROFILE_S3` (default `bilds2Dev`), `NODE_ENV` (`dev|production|test|local`),
`BIM_STORAGE` (`s3|local`, default `s3`), `ENABLE_CRON_JOBS` (`true|false`, default
`false`), `API_SERVER_PORT` (3333), `SECURITY_*`.

**O que falta no `S3Service` para este trabalho** (métodos aditivos, sem quebrar nada):

| Método | Para quê | Comando AWS |
|---|---|---|
| `headObject(key)` | `stat()` do `GeometryStore` — decidir 304 sem baixar bytes | `HeadObjectCommand` |
| `uploadStream(stream, key, contentType, contentLength)` | subir o `.aq` de 618 MB sem carregar em memória | `PutObjectCommand` com `Body: ReadStream` + `ContentLength` (PUT simples suporta até 5 GB — **não precisa de `@aws-sdk/lib-storage`**) |
| `downloadToFile(key, destPath)` | worker baixar o `.aq` para o disco efêmero | `GetObjectCommand` + `pipeline()` |
| `uploadBuffer` com `ContentEncoding` | geo gzipado (ganho medido de **5,8×**) | parâmetro extra opcional |

> **Não adicione dependência nova sem `pnpm audit` imediatamente depois** — regra da casa,
> e `@aws-sdk/lib-storage` é justamente a que dá vontade de instalar e não é necessária.

### 3.6 Trabalho assíncrono: o padrão da casa

**Não existe Redis, BullMQ, SQS ou qualquer fila dedicada no projeto.** Verificado:
`apps/api/package.json` não tem `bullmq`, `ioredis`, `@nestjs/bull` nem
`@aws-sdk/client-sqs`; `CacheModule.register()` aparece uma única vez
(`payments.module.ts`) com store em memória.

O padrão estabelecido, e a decisão já tomada por tech-lead em outro módulo, é
**coleção MongoDB como log de jobs + claim atômico + `@Cron` varredor**:

`apps/api/src/webhooks-outbound/services/webhook-delivery-processor.service.ts`

```typescript
/**
 * Sem fila dedicada (Bull/BullMQ) — decisão do tech-lead. O claim atômico em
 * WebhookDeliveriesRepository.claimNextBatch garante que múltiplas réplicas
 * da API não disparem a mesma entrega duas vezes.
 */
@Cron(DELIVERY_CRON_EXPRESSION, { name: 'webhook-outbound-delivery-processor' })
async processDueDeliveries(): Promise<void> {
  if (this.envService.get('ENABLE_CRON_JOBS') !== 'true') return
  const batch = await this.deliveriesRepository.claimNextBatch(DELIVERY_BATCH_SIZE, DELIVERY_LOCK_TIMEOUT_MS)
  if (batch.length === 0) return
  await Promise.all(batch.map((d) => this.processDelivery(d)))
}
```

E o claim (`repositories/webhook-deliveries.repository.ts:61`), que é o trecho a copiar:

```typescript
const dueFilter = {
  nextAttemptAt: { $lte: now },
  $or: [
    { status: { $in: [PENDING, FAILED] } },
    { status: PROCESSING, lockedAt: { $lte: lockExpiredBefore } },  // retoma lock expirado
  ],
}
const candidates = await this.model.find(dueFilter).sort({ nextAttemptAt: 1 }).limit(limit).select('_id').lean()
for (const c of candidates) {
  const claimed = await this.model.findOneAndUpdate(
    { _id: c._id, ...dueFilter },                                   // ← o filtro repetido é o que torna atômico
    { $set: { status: PROCESSING, lockedAt: now } },
    { new: true },
  )
  // ...
}
```

Três propriedades desse desenho que interessam ao import BIM: sobrevive a restart de pod
(o lock expira e outro pod reclama), é seguro com N réplicas, e não introduz
infraestrutura nova.

**Regra obrigatória de cron** (`bilds.com/CLAUDE.md` e `docs/architecture/patterns.md:1292`):
todo método `@Cron` começa com a trava `ENABLE_CRON_JOBS`, injeta `EnvService`, e usa
`{ name: 'slug-kebab-case', timeZone: 'America/Sao_Paulo' }`.

Também disponível e usado: `@nestjs/event-emitter` (`@OnEvent('profile.created')` etc.) —
bom para disparar o enfileiramento, ruim como transporte de trabalho pesado (é in-process
e morre com o pod).

### 3.7 Runtime: EKS, imagem, réplicas

Da `.github/workflows/development-api.yaml` (e os pares `staging-`/`production-`):

- Imagem construída de `apps/api/Dockerfile`, publicada no **ECR** (`bilds-api-dev`),
  deploy com `kubectl set image deployment/bilds-api-dev api=$IMAGE -n dev` em **EKS**
  (`bilds-dev-eks`), região `us-east-1`. Credencial por OIDC (`role-to-assume`).
- `cp apps/api/.env.staging apps/api/.env` no build — env em arquivo, dentro da imagem.

Do `apps/api/Dockerfile`:

```dockerfile
FROM node:24-alpine AS base          # ← Alpine/musl
...
RUN turbo prune api --docker
RUN pnpm install --ignore-scripts    # ← postinstall NÃO roda
RUN pnpm turbo build --filter=api...
FROM base AS runner
RUN adduser --system --uid 1001 nestjs
USER nestjs                          # ← não-root
CMD NODE_ENV=production node apps/api/dist/src/main.js
```

Quatro consequências duras, todas relevantes:

1. **`node:24-alpine` = musl.** O **Playwright não suporta Alpine** (os builds do Chromium
   distribuídos pelo Playwright são glibc). A miniatura fiel exige Chromium. Isso é o
   maior desvio da POC para a produção — ver §5.4 e §10 (**D-2**).
2. **`pnpm install --ignore-scripts`** — se `playwright` entrar como dependência da API, o
   postinstall que baixa o browser **não roda**. Precisaria de `RUN npx playwright install
   chromium` explícito, num base image glibc.
3. **`USER nestjs` (uid 1001), sem privilégio de namespace** — Chromium precisa de
   `--no-sandbox` (a POC já usa: `SWIFTSHADER_ARGS` em
   `bilds-bim-3d/www/tools/thumb-rasterizer.ts`).
4. **Prod roda JS compilado (`dist/src/main.js`), não `ts-node`.** A POC forka workers com
   `execArgv: ['--require', 'ts-node/register/transpile-only', ...]` e
   `path.resolve(__dirname, 'parse-worker.ts')`. **Em produção o caminho é `.js` e não há
   ts-node.** Se o modelo de execução usar `fork()`, o alvo tem que ser resolvido de forma
   que funcione nos dois ambientes (ex.: `path.join(__dirname, 'parse-worker' + path.extname(__filename))`)
   — é um erro que passa em dev e explode em produção.

Sem manifesto k8s no repositório: **limites de memória, CPU e `ephemeral-storage` do pod
são desconhecidos daqui** e precisam ser confirmados com quem opera o cluster antes de
assumir que um parse de 618 MB caiba (§10, **D-3**).

Observabilidade disponível: `dd-trace` inicializado em `main.ts` (Datadog) e `Logger` do
Nest. Use os dois — o pipeline é assíncrono e sem log estruturado fica cego.

### 3.8 Convenções que reprovam em review

Resumo do que `bilds.com/CLAUDE.md` exige. Não são preferências:

**Backend**

- ❌ `process.env.X` direto — ✅ `this.envService.get('X')`, e **toda var declarada em
  `config/env/env.ts`** com tipo Zod e default seguro.
- Ordem obrigatória ao criar endpoint: **Module → Controller → Service → DTO → Tests**.
- DTO com `class-validator` sempre; nunca `req.body` cru no service.
- **`@IsIn(ARRAY)`, nunca `@IsEnum(['a','b'])`** para arrays JS — `@IsEnum` com array
  literal aceita `'0'`, `'1'` como válidos (usa `Object.keys`). Detalhe: o
  `UpdateLayoutDto` existente usa `@IsEnum(['series-rows','catalog-grid'])` — bug latente
  já no código, não copie.
- Exceptions tipadas (`NotFoundException`, `BadRequestException`, `ForbiddenException`,
  `ConflictException`); nunca expor stack.
- `@ApiOperation()` + decorators de response em todo endpoint.
- Soft delete (`deletedAt: null`) em toda query — exceto `bim_catalogs`, que é hard delete
  por decisão explícita (KTD-5).
- Services injetam repositories; nada de `new`; nada de dependência circular.
- Cron sempre com a trava `ENABLE_CRON_JOBS`.
- ❌ CORS por controller — o global em `main.ts` cobre.
- `EnvService` **explicitamente no array `providers`** de qualquer módulo que use
  `S3Service` (KTD-6; sem isso: `UnknownDependenciesException` no startup).

**Frontend**

- **i18n obrigatório em todo texto visível**, nos três locales
  (`apps/web/public/locales/{pt,en,es}/common.json`). Sem exceção: botão, label,
  placeholder, toast, estado vazio, mensagem de erro. Só conteúdo de banco é isento.
- ✅ Tailwind sempre; ❌ `style={{}}` inline. (O admin do BIM 3D atual está cheio de inline
  style — é dívida existente, não licença.)
- Server Component por padrão; `'use client'` só quando precisa.
- Dados dinâmicos: **RTK Query** no container. `page.tsx` fino: `generateMetadata` +
  JSON-LD com `React.cache()`, render delegado ao container.
- **Todo arquivo novo em `queries/` exige registrar a tag em `queries/index.ts`
  (`tagTypes`)** — quebra o build se esquecer. `'BimCatalog'` já está registrada
  (`apps/web/src/queries/index.ts:89`).
- Skeleton com `animate-pulse`; nunca `@keyframes` próprio.
- JSON-LD: `<SchemaMarkupStatic>` em Server Component, `<SchemaMarkup>` em Client.
- ❌ `as unknown as X`.
- Validação em duas camadas: Zod no front (`schemas/`) + `class-validator` no back.

**Git**

- ❌ Commit direto em `develop`. Feature branch + PR.
- `git push` no repo tem pre-push hook que roda `turbo build` (~2 min): use timeout
  generoso; se a primeira tentativa expirar, repetir passa (cache do turbo).

---

## 4. O que a POC provou — o núcleo transferível

A POC (`bilds-bim-3d`, 17 sessões, encerrada em 2026-08-31) respondeu cinco perguntas com
medição. O destilado está em
`bilds-bim-3d/docs/solutions/architecture-patterns/poc-catalogo-bim-dinamico-aprendizados.md`.
Esta seção traz o que precisa atravessar para a bilds.com.

### 4.1 Divisão de dados e a interface de storage

**Geometria e miniatura vivem em storage de arquivo; o MongoDB guarda ponteiro.** Guardar
geometria como `BinData` foi avaliado e recusado: mata o codec binário, bate no teto de
tamanho de documento e impede servir por HTTP com cache.

O documento de produto guarda `geoKey` e `thumbKey`. A interface real da POC
(`bilds-bim-3d/www/apps/api/src/geometry-store/geometry-store.interface.ts`) tem **cinco**
métodos — o `stat()` foi adicionado em S6.1 e **falta no documento de aprendizados**, que
descreve só quatro:

```typescript
export interface AssetStat { size: number; mtimeMs: number }

export interface IGeometryStore {
  put(key: string, data: Buffer): Promise<void>
  get(key: string): Promise<Buffer>
  /** Metadados sem ler os bytes — permite decidir 304 antes de tocar no blob. */
  stat(key: string): Promise<AssetStat>
  delete(key: string): Promise<void>
  deleteByPrefix(prefix: string): Promise<void>
}
```

`DiskGeometryStore` valida toda chave contra traversal
(`path.resolve(baseDir, key).startsWith(baseDir + path.sep)`, erro `ETRAVERSAL`) — a
`S3GeometryStore` precisa do equivalente (`path.basename` / regex de chave), porque uma
chave com `../` no S3 não escapa do bucket mas escapa do **prefixo** e pode sobrescrever
outro catálogo.

Injeção por token de string na POC:
`{ provide: 'GEOMETRY_STORE', useClass: DiskGeometryStore }`. Na bilds.com, use um
provider de fábrica escolhendo por `BIM_STORAGE` — a flag já existe.

### 4.2 Leitura do `.aq` — `aq-reader.ts`

`bilds-bim-3d/www/tools/aq-reader.ts` (315 linhas). Duas funções exportadas:
`extract(aqPath): AqData` e `extractSimboloias(aqPath): AqSimboloiasResult`.

**Abertura.** Tenta SQLite direto (`new DatabaseSync(path)` de `node:sqlite`, validando com
`SELECT 1 FROM GRUPO_PECA LIMIT 1`); se falhar e o arquivo começar com `PK`, extrai o
SQLite de dentro do ZIP percorrendo os Local File Headers com `zlib.inflateRawSync`,
grava em `os.tmpdir()` e abre de lá (com cleanup).

> `node:sqlite` **exige caminho de arquivo em disco**. Não há como parsear de stream ou
> buffer. Consequência direta: o `.aq` tem que estar no filesystem do processo que
> parseia. Um `.aq` em ZIP escreve **uma segunda cópia** em `/tmp` — planeje até ~2× o
> tamanho do arquivo em disco efêmero.

**Encoding: cp1252, não UTF-8, não latin-1.**

```typescript
const decoder = new TextDecoder('windows-1252')
// ...
'SELECT ID_PECA, CAST(NOME_PECA AS BLOB) AS nome_blob, ... FROM PECA WHERE ATIVO = 1'
```

Toda coluna de texto é lida com `CAST(col AS BLOB)` e decodificada com
`TextDecoder('windows-1252')`. Latin-1 e cp1252 são idênticos **exceto** na faixa
0x80–0x9F, que é exatamente onde vivem travessão (0x96), aspas curvas (0x93/0x94) e
reticências (0x85). Lido como latin-1, `5U – 19” x 570mm` chega na página pública como
`5U \x96 19\x94 x 570mm`. **Falha silenciosa** — latin-1 nunca lança. O `TextDecoder` do
Node também não lança nos cinco bytes indefinidos do cp1252 (0x81, 0x8D, 0x8F, 0x90, 0x9D),
o que é mais robusto que o `decode` do Python.

**Tabelas usadas** (as que importam):

| Tabela | Papel |
|---|---|
| `GRUPO_PECA` | séries/famílias (`NOME_GP`); filtra `ATIVO = 1` |
| `PECA` | variantes (`NOME_PECA`, `DESCRICAO_DADOS`, dimensões em cm); filtra `ATIVO = 1` |
| `DADOS_HIDRAULICOS` + `MODELO_BOMBA` + `ITEM_CURVA_BOMBA` | curva Q-H (`VAZAO_ICB`, `ALTURA_ICB`, `POTENCIA_ICB`, `RENDIMENTO_ICB`) e potência nominal. **Ausentes em biblioteca não-hidráulica — o `try/catch` em volta é obrigatório** |
| `PROPRIEDADE_PERSONALIZADA` + `VALOR_PROPRIEDADE_PERSONALIZADA` + `GRUPO_...` | specs livres, em `try/catch` pelo mesmo motivo |
| **`SIMBOLOGIA_3D`** | a malha. Colunas: `SIMBOLOGIA_3D` (BLOB OQ3D), `IMAGEM` (BMP 100×100 pré-renderizado pelo AltoQi), `WIREFRAME`, `NOME` |
| **`PECA_SIMBOLOGIA_3D`** | vínculo peça → malha. **Chave estrangeira: dispensa qualquer matching por nome** |
| `GRUPO_SIMBOLOGIA_3D` / **`CLASSE_SIMBOLOGIA_3D`** | `NOME_CLASSE` no padrão `"FABRICANTE - Linha"` → de onde saem `manufacturer` e `title` do catálogo |
| `ENTRADA_3D` | pontos de conexão hidráulica com posição e diâmetro. **O IFC não carrega isso.** Ainda não consumido — oportunidade futura |

> **Nunca `SELECT *` em `SIMBOLOGIA_3D`.** A coluna `WIREFRAME` é **69–71% do arquivo**
> (285 MB dos 412 MB da Amanco) e é inútil para viewer web. Selecione colunas
> explicitamente. Este único erro multiplica por 3 o consumo de memória do parse.

**Peças sem geometria são normais.** Sem linha em `PECA_SIMBOLOGIA_3D` significa peça sem
forma fixa: tubos (o AltoQi gera o cilindro de diâmetro × comprimento) e kits sanitários.
Na Amanco são **312 de 1.168 (27%)**. Pular é o comportamento correto — e informar quantas
foram puladas é o comportamento útil (candidato a campo do documento de import).

### 4.3 A geometria OQ3D — `oq3d-parser.ts`

`bilds-bim-3d/www/tools/oq3d-parser.ts` (388 linhas). Exporta `isOQ3D(buf)`, `parse(buf)`,
`toBuffers(buf, skipMarkers?)` e a classe de erro `OQ3DError`.

**Formato:** árvore de objetos serializada estilo Delphi.

```
0x5B <len:u32> <ClassName>   abre objeto
...payload...
0x5D                         fecha
```

Sete classes carregam dado (`CLASSES` no parser): `TQi3DReusedObject`,
`TQi3DReusableObject`, `TQi3DObjectGroup`, `TQi3DTriangleMesh`, `TCoatingColor`,
`TQi3DIndexedTriangleMeshData`, `TCoordinateTransformation3D`.

```
TQi3DIndexedTriangleMeshData
    u32 versao(=2) | u32 nCoords | u32 reservado
    nCoords doubles                → nCoords/3 vértices (x,y,z)
    u32 nIdx | u32 reservado
    nIdx u32                       → nIdx/3 triângulos
TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A     (cor UNIFORME da malha)
TCoordinateTransformation3D
    u32 versao | 12 doubles        → rotação 3×3 COLUMN-major + translação
```

**Os dois bugs que custaram uma sessão inteira (S5.1) e estão resolvidos no código:**

1. **A rotação é column-major.** O elemento `(i, j)` está em `raw[j*3 + i]`. Lida como
   row-major sai **transposta** — e o efeito é traiçoeiro: a **contagem de triângulos não
   muda**, só a posição. Uma peça fica "solta no ar". O parser transpõe já na leitura:
   ```typescript
   const rot = [raw[0], raw[3], raw[6], raw[1], raw[4], raw[7], raw[2], raw[5], raw[8]]
   ```
2. **`TQi3DReusedObject` normalmente não traz a definição inline** — referencia uma
   `TQi3DReusableObject` já serializada, pelo **índice de serialização (base 1) contado
   sobre todos os objetos da árvore em ordem de documento**. O GUID é único por instância e
   **nunca** foi a chave. Layout:
   ```
   +0   u32 versão (2 ou 3)
   +28  u32 tamanho do GUID (sempre 36)
   +32  GUID, 36 bytes ASCII        ← único por instância
   ...  bloco de 15 bytes (v2) ou 16 (v3)
   +B   u8 discriminador: 0x02 = definição inline | 0x01 = seguem 4 bytes de referência
   ```
   Validado: **2.960 `TQi3DReusedObject`, dos quais 1.096 por referência — todos
   resolvem.** Ignorar isso perde **~31% dos triângulos** na Amanco.

**Unidades e eixos.** OQ3D é **centímetros, Z-up**. Saída para Three.js é **metros, Y-up**:

```
THREE.x =  OQ3D.x * 0.01
THREE.y =  OQ3D.z * 0.01     ← Z vira Y
THREE.z = -OQ3D.y * 0.01     ← Y inverte e vira Z
```

O fator 0,01 é o erro mais fácil de cometer: o OQ3D grava em cm, ao contrário do IFC.
Esquecê-lo produz um modelo 100× maior.

**Cores de marcador.** Verde `(1,154,63)`, azul `(10,84,152)` e `(0,116,232)` são bocais de
conexão do AltoQi, não produto — inflam a bounding box (~2 cm) e portanto **mudam o
enquadramento da câmera da miniatura**. `toBuffers(blob, skipMarkers = true)` remove, com
fallback para o conjunto completo se sobrar vazio. **A POC chama `toBuffers(blob)` sem o
flag** (`parse-worker.ts`): decidir se a bilds.com deve ligar (§10, **D-7**).

**Robustez.** O parser lança `OQ3DError` (não retorna silenciosamente, como o Python) para
blob sem assinatura, contagem declarada maior que o buffer e blob truncado — **e valida
antes de alocar qualquer array proporcional à contagem declarada**. Isso é defesa contra
`.aq` malicioso e precisa ser mantido: o `.aq` passa a ser entrada de usuário.

**Correspondência com o IFC** (útil para validar, não para produzir):

| OQ3D | IFC4 |
|---|---|
| `TQi3DObjectGroup` | `IFCELEMENTASSEMBLY` |
| `TQi3DReusableObject` | `IFCREPRESENTATIONMAP` |
| `TQi3DReusedObject` | `IFCMAPPEDITEM` |
| `TQi3DIndexedTriangleMeshData` | `IFCTRIANGULATEDFACESET` |
| `TCoordinateTransformation3D` | `IFCLOCALPLACEMENT` |
| `TCoatingColor` | `IFCINDEXEDCOLOURMAP` |

A contagem de entidades bate exatamente (18 `TQi3DReusedObject` ↔ 18 `IFCMAPPEDITEM`).

### 4.4 Deduplicação de vértices — obrigatória

`dedupBuffers()` em `bilds-bim-3d/www/apps/api/src/importacoes/parse-worker.ts`.

- **Sem dedup a geometria fica ~4× maior.** Dancor: 182,7 MB → **44,7 MB**. Medido também
  por peça: CAM-W21 2CV vai de 82.275 para 16.488 vértices (**-80%**).
- A chave é **posição + cor quantizadas em float32**, nunca só a posição:
  ```typescript
  key = hasCol
    ? `${f32bits(px)},${f32bits(py)},${f32bits(pz)},${f32bits(cr)},${f32bits(cg)},${f32bits(cb)}`
    : `${f32bits(px)},${f32bits(py)},${f32bits(pz)}`
  ```
  Sem a cor na chave, dois vértices na mesma posição com cores diferentes (a fronteira
  entre o corpo vermelho e o logo branco de uma bomba) são fundidos e uma cor desaparece.
- A quantização usa **a mesma precisão do `Float32BufferAttribute` do Three.js** — é o que
  garante que o dedup não introduz costura visível no render.
- Validado contra o `dedup.py` de referência: mesmo total de bytes.
- **O import ativo do Dancor na POC foi feito antes do dedup existir.** Daí o item
  "re-processamento de imports legados" na lista de obrigatórios. Na bilds.com isso
  significa: **o pipeline precisa de uma rota de reprocessamento desde o começo**, e o
  documento de import deve registrar a versão do parser/pipeline que o gerou.

### 4.5 Miniaturas — ADR-004, e não negocie a fidelidade

Histórico curto: o ADR-003 escolheu um rasterizador software em TypeScript (65 ms/geo,
4,3 KB) por ser 3,7× mais rápido e não exigir Chromium. **Foi revertido em S4.4**, porque
o dono do produto recusou o resultado visual.

Medição contra um render do viewer real, mesma câmera e tamanho:

| Abordagem | PSNR vs viewer | Tempo | Observação |
|---|---|---|---|
| Rasterizador software (flat shading) | **27 dB** | 65 ms/geo | silhueta chapada |
| **Chromium + Three.js real** | **47 dB** | ~370 ms/geo | 47 dB é o **piso** imposto pela compressão WebP q=0,85 |

> **Não reimplemente o render fora do Three.js.** O que gera a miniatura tem que ser o
> **mesmo `buildScene()` e a mesma câmera** do viewer, dirigidos em browser headless.
> Qualquer reimplementação produz imagem *parecida*, e o catálogo passa a ter dois visuais
> conforme o produto tenha ou não miniatura pronta.

Isso é literalmente verificável hoje: `buildScene()` em
`bilds.com/apps/web/src/components/b-bim-3d/bim-viewer-engine.ts` e o `buildScene()` do
harness `bilds-bim-3d/templates/thumbs/harness.html` são **idênticos linha a linha**
(material `MeshStandardMaterial` com `metalness: 0.25, roughness: 0.55`, `vertexColors` se
houver cor, cor base `0x8896aa` quando não houver; `AmbientLight(0xffffff, 0.7)` +
`DirectionalLight(0xffffff, 0.9)` em `(2,3,2)` + `DirectionalLight(0xc8d8f0, 0.35)` em
`(-2,1,-1)`).

**Formato de saída** (contrato consumido pelo `LazyBimCard` que já está em produção):

| Propriedade | Valor |
|---|---|
| Container | WebP |
| Dimensão | **448 × 324** (2× o card de 224×162, para DPR 2) |
| Qualidade | 0,85 |
| Fundo | `#F3F4F6` opaco (`setClearColor`, o mesmo `bg-gray-100` do card) |
| Câmera | `PerspectiveCamera(38, W/H, 0.001, 500)`, posição `(size*0.85, size*0.32, size*0.85)`, `lookAt(0,0,0)`, `size` = diagonal da bbox |
| Renderer | `antialias: false, alpha: false, preserveDrawingBuffer: true`, `setPixelRatio(1)` |
| Tamanho típico | **~4 KB** (medido em 622 geometrias / 9 catálogos) |

O fundo opaco é deliberado: o `<img>` usa **`object-contain`** (não `fill`), e a sobra
some porque tem a mesma cor do card. Com `fill` a peça estica em card largo.

**As duas otimizações que fazem a diferença entre 24,5 s e 6,2 s num lote de 13:**

1. **Um browser por processo, reaproveitado no lote.** A subida (~1 s) amortiza no lote
   inteiro em vez de ser paga por miniatura. `bilds-bim-3d/www/tools/thumb-rasterizer.ts`
   guarda a sessão num singleton (`sessionPromise`) e serializa os renders numa fila
   (`enqueue`), porque há **um único contexto WebGL por página**.
2. **Passe a geometria como STRING JSON para `page.evaluate`, nunca como objeto.** O
   serializador do Playwright anda o grafo do objeto; uma geometria é um array de centenas
   de milhares de números. Medido numa peça de 4,8 MB (35 k vértices, 52 k triângulos):
   **objeto ~2.200 ms, string JSON ~370 ms** — dos quais só ~120 ms é o render WebGL.
   (`JSON.stringify` custa ~40 ms; `JSON.parse` do outro lado ~13 ms.)

**Outros detalhes operacionais do renderizador da POC que não são opcionais:**

- **`closeThumbRenderer()` antes de sair do processo.** Sem isso o Chromium fica órfão e o
  handle do servidor HTTP prende o exit.
- **O harness é servido por HTTP efêmero (`listen(0)`), não `file://`** — o Chromium recusa
  `import` de módulo ES sobre `file://` por CORS, e o harness carrega o Three.js por
  importmap.
- Sem GPU (WSL, container, CI) o WebGL headless só sobe por SwiftShader:
  `['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--no-sandbox']`.
- Falha ao subir o Chromium por biblioteca de sistema ausente
  (`libnss3 libnspr4 libasound2t64`) vem enterrada em centenas de linhas de stack — a POC
  extrai a linha acionável com regex. Vale copiar o tratamento.
- Custo por consumidor: **~200 MB de Chromium** por processo.

**Uma miniatura por geometria, não por produto.** Produtos diferentes compartilham malha, e
a câmera deriva só da bbox → mesma geometria dá miniatura idêntica. Amanco: 856 produtos,
**448 geometrias**. Intelbras: 32 produtos, 18 geometrias. **A POC gera por produto
(`thumbs/{importId}/{productId}.webp`) e desperdiça ~48% do trabalho na Amanco.** Ver §5.5:
chave por conteúdo resolve isso de graça.

**Retrocompatibilidade já implementada no consumidor:** `thumbBaseUrl` pode ser `null` e um
produto pode não ter `thumb` — nos dois casos o `LazyBimCard` cai no render dinâmico
(comportamento legado, o de 39,9 s de LCP). Ou seja: **miniatura ausente não quebra a
página, só a deixa lenta.** Isso permite publicar o catálogo antes das miniaturas
terminarem — e é exatamente o que o pipeline deve fazer.

### 4.6 Máquina de estados do import

`bilds-bim-3d/www/apps/api/src/bim-imports/bim-imports.schema.ts` +
`importacoes.service.ts`:

```
recebido → parseando → gravando → publicado
                              ↘ vazio      (arquivo lido, nenhuma peça com geometria)
                              ↘ falhou     (com mensagem em `error`)
```

Documento: `_id` (uuid), `companyId`, `catalogId`, `status`, `error`, `note`,
`productCount`, `fileName`, `createdAt`, `updatedAt`. Índice `{ companyId, status }`.

Comportamentos que devem atravessar:

- **`vazio` é sucesso, não erro.** Biblioteca só de tubos/kits não tem geometria. A UI da
  POC explica isso ao usuário em vez de mostrar falha.
- **Cleanup no `falhou`:** `store.deleteByPrefix('geo/{importId}')` +
  `productModel.deleteMany({ importId })`. Sem isso sobra binário órfão pago por mês.
- **`finally { fs.unlink(aqPath) }`** — o arquivo temporário sai sempre.
- **Upsert de catálogo com substituição:** se já existe catálogo com o mesmo
  `(companyId, slug)`, atualiza o catálogo, insere os produtos do novo import, apaga os
  produtos do import anterior (`deleteMany({ catalogId, importId: { $ne: importId } })`) e
  apaga os arquivos do prefixo antigo, registrando em `note` o que foi substituído. A
  troca é **atômica do ponto de vista do leitor** porque o produto novo entra antes do
  velho sair.
- **Miniaturas são fire-and-forget e não mudam o status.** `spawnThumbWorker(...).catch(() => {})`
  depois de `publicado`. Falha de miniatura nunca bloqueia publicação.
- **Recuperação na UI:** ao carregar a página, busca a última importação
  (`GET /importacoes/ultima`) e retoma o polling se ela não estiver em estado terminal.
  Sem isso, um F5 no meio de um parse de 2 min deixa o usuário sem informação nenhuma.

**O bug de IPC que só aparece em escala** — vale como regra de review:

```typescript
// ERRADO — perde o payload em resposta grande
process.send!(result)
process.exit(0)

// CORRETO — sai só depois do flush do IPC
process.send!(result, () => process.exit(0))
```

Com 13 produtos (Dancor) o `send` era síncrono na prática e nunca falhou. Com 856
(Amanco), `child.on('message')` **nunca disparava** e o import ficava preso em `parseando`
até o timeout de 5 min. Silencioso.

**Upload em disco, não em memória.** `importacoes.controller.ts`:

```typescript
// .aq são SQLite raw: Dancor ~153 MB, Amanco ~394 MB, Maxbar ~618 MB.
// diskStorage evita buffer inteiro em RAM; multer escreve direto em /tmp.
const MAX_FILE_BYTES = 750 * 1024 * 1024
const storage = diskStorage({
  destination: (_req, _file, cb) => cb(null, os.tmpdir()),
  filename: (_req, _file, cb) => cb(null, `bim-${crypto.randomUUID()}.aq`),
})
```

### 4.7 Cache de assets

`bilds-bim-3d/www/apps/api/src/common/asset-cache.ts` — resultado de S6.1, e a razão é a
parte que interessa:

As chaves do store são `<tipo>/<importId>/<productId>` — derivadas do **import**, não do
**conteúdo**. Um `thumb:regen` sobre o mesmo import reescreve os bytes na mesma chave. Com
ETag derivada só da chave **mais `Cache-Control: immutable`**, o browser servia a
miniatura velha por um ano — e trocar só a ETag não resolveria, porque com `immutable` ele
nem revalida.

Solução aplicada:

```typescript
export const ASSET_CACHE_CONTROL = 'public, max-age=0, must-revalidate'
export function assetEtag(key: string, stat: { size: number; mtimeMs: number }): string {
  return `"${crypto.createHash('sha1').update(`${key}:${stat.size}:${stat.mtimeMs}`).digest('hex').slice(0, 16)}"`
}
```

E o 304 é decidido **antes de ler o blob** (só o `stat`): geometria de 2,7 MB não sai do
disco à toa. Medido: `200` ≈ 35 ms, `304` ≈ 29 ms e 0 bytes.

`mtime + size` em vez de hash do conteúdo é escolha consciente: hashear obrigaria a ler o
arquivo inteiro para responder "não mudou". O preço é um `200` extra quando os bytes são
idênticos e o mtime mudou — nunca conteúdo errado.

> **E a recomendação que S6.1 deixou explicitamente para a bilds.com:** com CDN na frente,
> o padrão certo **não** é `must-revalidate` — é **URL content-addressed** (hash do
> conteúdo na chave) com `immutable`. O `must-revalidate` era o suficiente-para-POC. Ver
> §5.5, onde isso vira a recomendação principal.

### 4.8 Números medidos — para orçar e para conferir depois

**Parse:**

| Implementação | Tempo (13 produtos Dancor) | Memória (Δ RSS) |
|---|---|---|
| Worker Python (S2.1) | ~39.000 ms | +189 MB |
| **Port TypeScript (ADR-002)** | **658 ms** | **+422 MB** |

59× mais rápido, 2,2× mais memória. A memória é **o risco operacional principal**; o
primeiro candidato de otimização é trocar `Array<[number,number,number]>` por
`Float64Array` na representação interna de vértices.

**Tamanhos:**

| Item | Valor |
|---|---|
| `.aq` de entrada | Dancor ~153 MB · Amanco ~394 MB · Maxbar ~618 MB |
| Geometria Dancor (13 produtos, com dedup) | 44,7 MB (sem dedup: 182,7 MB) |
| Geometria Amanco (856 produtos, com dedup) | 248 MB |
| Storage total da POC (869 produtos, 2 catálogos) | 363 MB, 1.696 arquivos |
| Miniaturas: 9 catálogos em produção | 348,2 MB de geometria → **2,5 MB** de miniaturas (razão 136×, chegando a 620× na Dancor) |
| Geo com gzip | razão medida **5,8×** — pior caso de página cai de 40 MB para ~7 MB |
| Custo S3 projetado | 200 catálogos × 250 MB = 50 GB ≈ **US$ 1,15/mês** |

**Página:**

| Sinal | Estático (CDN) | POC (banco/SSR) |
|---|---|---|
| HTML inicial | 44 KB | 71,9 KB (1,6×) |
| 13 miniaturas | ~56 KB | 57,3 KB (igual) |
| TTFB | ~50 ms (edge) | 177–254 ms medido; 150–300 ms estimado em prod |
| Tempo até o primeiro card | ~100 ms | ~280–380 ms |

O LCP real de 39,9 s medido com Lighthouse em produção
(`bilds.com/dancor/bombas-incendio`, 2026-08-27) era **antes** das miniaturas prontas: o
elemento LCP era o `<img>` do card, produzido no browser (baixa geometria → monta
`BufferGeometry` → WebGL → `toDataURL`), com **7.230 ms de element render delay**, 3,75 MB
de geometria para **2 cards** em viewport mobile, sem compressão, página de 6.610 KiB
(57% geometria). Com miniatura pronta: zero geometria e zero WebGL no carregamento.

**Escala:** MongoDB é trivial para esse volume de documentos (200 catálogos ≈ 2.600
produtos). O limitador é storage de arquivo — e é barato.

**O que ainda não foi medido e precisa ser, em produção:** LCP com Lighthouse real (o WSL
da POC não tem browser headless com DevTools para Web Vitals; os números de LCP da POC são
soma de componentes medidos com `curl`).

---

## 5. Arquitetura recomendada na bilds.com

Cada subseção traz **o que existe**, **as opções**, **a recomendação** e **o que a
recomendação obriga**. Onde a decisão precisa de dono humano, há referência para §10.

### 5.1 Onde o código vive

Estender o módulo existente, não criar módulo paralelo — `bim_catalogs`, `assertPermission`,
`S3Service` e as rotas públicas já estão lá.

```
bilds.com/apps/api/src/b-bim-3d/
├── constants.ts                          (+ limites do .aq, versão do pipeline)
├── b-bim-3d.module.ts                    (+ novos providers/schemas)
├── schemas/
│   ├── bim-catalog.schema.ts             (alterado — §5.6)
│   ├── bim-product.schema.ts             (NOVO — coleção bim_products)
│   └── bim-import.schema.ts              (NOVO — coleção bim_imports)
├── repositories/
│   ├── bim-catalog.repository.ts
│   ├── bim-product.repository.ts         (NOVO)
│   └── bim-import.repository.ts          (NOVO — inclui claimNextBatch)
├── services/
│   ├── bim-catalog.service.ts            (intocado no caminho ZIP)
│   ├── bim-import.service.ts             (NOVO — criar import, consultar status)
│   ├── bim-import-processor.service.ts   (NOVO — cron + claim + orquestração)
│   ├── aq-parser.service.ts              (NOVO — porta aq-reader + oq3d-parser)
│   └── bim-thumb.service.ts              (NOVO — geração de miniatura)
├── storage/
│   ├── geometry-store.interface.ts       (NOVO — 5 métodos, §4.1)
│   ├── s3-geometry-store.ts              (NOVO)
│   ├── disk-geometry-store.ts            (NOVO — dev, BIM_STORAGE=local)
│   └── geometry-store.provider.ts        (NOVO — fábrica por BIM_STORAGE)
├── lib/                                  (código puro, sem Nest — testável isolado)
│   ├── aq-reader.ts                      (porta de bilds-bim-3d/www/tools/aq-reader.ts)
│   ├── oq3d-parser.ts                    (porta de .../oq3d-parser.ts)
│   └── dedup-buffers.ts                  (extraído do parse-worker da POC)
├── controllers/
│   ├── bim-catalog.controller.ts         (ATENÇÃO à ordem das rotas — KTD-3)
│   └── bim-import.controller.ts          (NOVO)
└── dtos/  (+ create-bim-import.dto.ts, bim-import-status.dto.ts, …)
```

**Por que `lib/` separado:** `aq-reader` e `oq3d-parser` são funções puras sobre `Buffer` e
caminho de arquivo. Fora do Nest, elas ganham teste unitário com fixture binária real, sem
`TestingModule`. Na POC isso viveu em `www/tools/` justamente por isso, e foi o que
permitiu conferir o parser contra o IFC.

Frontend:

```
bilds.com/apps/web/src/
├── queries/bim-import.ts                   (NOVO — registrar tag em queries/index.ts!)
├── containers/Company/EditCompany/steps/   (nova aba/step "Catálogo 3D")
└── components/b-bim-3d/                    (consumidor — ajustes de §5.9)

bilds.com/apps/admin/src/
├── queries/bim-catalog.ts                  (+ endpoints de import)
└── app/b-bim-3d/[companyId]/novo/          (adicionar o caminho .aq ao lado do ZIP)
```

### 5.2 Transporte do upload — a primeira decisão

**Restrições, todas verificadas:**

- `MediaUploader` já dá progresso real, e o endpoint está **hardcoded** em
  `queries/medias.ts` como `${NEXT_PUBLIC_API_URL}/files/upload`.
- `POST /files/upload` é **`@PublicAccess()`**, aceita até **1 GB** e usa
  **memoryStorage**.
- `.aq` **não está** em `ALLOWED_UPLOAD_EXTENSIONS`.
- A regra da casa é que o DTO de entidade receba **URL**, não binário.
- `node:sqlite` precisa do arquivo **em disco** do processo que parseia.
- O pod pode ser reciclado a qualquer momento (rolling deploy, scale-in).

**Opção A — usar `/files/upload` como está.** Adiciona `aq` ao allowlist global e ao
`EXTENSION_SIGNATURE_RULES`, depois `POST .../bim-imports { fileUrl }`.

- ✅ Zero mudança no `MediaUploader` e no `medias.ts`. Progresso de graça.
- ❌ **Abre upload anônimo de arquivos de até 1 GB de SQLite para o bucket.** É um regalo
  para abuso: sem sessão, com throttle global de 100 req/min.
- ❌ memoryStorage: 618 MB de `Buffer` no heap do pod da API, por upload concorrente.

**Opção B (recomendada) — endpoint dedicado e autenticado, com `diskStorage`.**

```
POST /companies/:id/bim-imports/upload      @VerifySession() + assertPermission
  FileInterceptor('file', { storage: diskStorage(os.tmpdir()), limits: { fileSize: 800MB } })
  → valida extensão + magic bytes (SQLite ou ZIP)
  → S3Service.uploadStream(createReadStream(tmp), `bim-imports/raw/{importId}.aq`, …)
  → fs.unlink(tmp)
  → 201 { url, importId, status: 'recebido' }   e enfileira o job
```

E no `MediaUploader`, uma mudança **aditiva de ~6 linhas** no mesmo espírito de
`allowedExtensions`: prop opcional `uploadEndpoint?: string`, repassada a
`uploadMedia({ ..., endpoint })`, com `xhr.open('POST', `${baseUrl}${endpoint ?? '/files/upload'}`)`.

- ✅ Superfície pública inalterada; upload exige sessão e permissão na empresa.
- ✅ `diskStorage` — nada de 618 MB em memória.
- ✅ Um round-trip: o import já nasce com o upload.
- ✅ `MediaUploader` continua sendo o componente, com o progresso que já tem.
- ⚠️ Requer a mudança aditiva no uploader e no `medias.ts` (revisável, testável).
- ⚠️ `.aq` **não** entra no allowlist global — bom: reduz superfície.

**Opção C — PUT pré-assinado direto do browser para o S3.**

- ✅ O byte nunca passa pela API. Melhor para arquivo grande.
- ❌ `MediaUploader` não sabe fazer isso (posta multipart para a API); exigiria caminho
  paralelo, CORS no bucket e validação de conteúdo só depois do upload.
- ❌ Contradiz o pedido de reusar o componente.

**Recomendação: Opção B.** Se o tech-lead recusar a mudança no `MediaUploader`, o fallback
é a Opção A **com** `@Throttle` específico e limite de tamanho por extensão — mas registre
o risco do upload anônimo (§10, **D-1**).

**Guardar o `.aq` bruto no S3 é parte da recomendação**, não detalhe:

| Motivo | Consequência |
|---|---|
| O worker pode ser outro pod | Sem o objeto compartilhado, o `/tmp` do pod que recebeu é inalcançável |
| Pod reciclado no meio do parse | O job é reclamado por outro pod e o arquivo ainda está lá |
| Reprocessamento sem novo upload | Fecha o item "re-processing de imports legados" da lista de obrigatórios |
| Dedup por conteúdo | `sourceHash` (sha256) evita reprocessar o mesmo arquivo |

Chave: `bim-imports/raw/{importId}.aq`. **Defina uma lifecycle rule no bucket** (ex.:
expirar em 90 dias) — 618 MB por import acumula. Isso é configuração de infra, não de
código (§10, **D-4**).

### 5.3 Indicação de progresso

**Opções:** SSE (`text/event-stream`), WebSocket, ou polling.

**Recomendação: polling**, como na POC. Razões concretas, não preferência:

- Com N réplicas atrás de um ingress, uma conexão SSE/WS fica presa **no pod que a
  aceitou** — e o trabalho está em outro pod. Fazer SSE funcionar exigiria pub/sub
  (Redis), que o projeto não tem.
- Não há gateway de WebSocket configurado no projeto (`@nestjs/platform-socket.io` não é
  dependência).
- RTK Query tem `pollingInterval` nativo, e a casa já é RTK Query.
- O progresso é grosso (segundos a minutos), não precisa de tempo real.

**Desenho:**

```typescript
// apps/web/src/queries/bim-import.ts
const { data } = useGetBimImportQuery(
  { companyId, importId },
  {
    pollingInterval: 3000,
    skipPollingIfUnfocused: true,
    skip: !importId || TERMINAL.includes(status),
  }
)
```

**O documento de import carrega os contadores** — é o que transforma "spinner eterno" em
progresso honesto:

| Campo | Alimentado por | Uso na UI |
|---|---|---|
| `status` | transições do processor | passo atual do tracker |
| `phase` | worker | rótulo fino ("lendo tabelas", "gravando geometrias") |
| `productsTotal` / `productsDone` | worker, a cada N peças | "142 de 856 produtos" |
| `thumbsTotal` / `thumbsDone` | worker de miniatura | segunda barra, após publicar |
| `startedAt` / `finishedAt` | processor | cronômetro (a POC mostra "há 1m 20s") |
| `skippedNoGeometry` | worker | explica "312 peças sem geometria 3D — normal" |
| `error` / `note` | processor | mensagem final |

Escreva o contador **em lote** (a cada ~50 itens, como a POC loga), não por item: 856
`findByIdAndUpdate` seriais custam mais que o parse.

**Reaproveite a UI da POC** — `bilds-bim-3d/www/apps/web/src/app/empresa/importar/page.tsx`
é um bom protótipo funcional (step tracker com estados feito/ativo/pendente, barra linear,
cronômetro, caixas de sucesso/aviso/erro, botão "tentar novamente"). **Mas ela é escrita
com `style={{}}` inline e strings hardcoded em português** — as duas coisas são proibidas
na bilds.com. Porte a **lógica e os estados**; refaça a apresentação em Tailwind com
`t()` nos três locales.

**Recuperação no reload é requisito, não extra.** `GET /companies/:id/bim-imports/latest`
(equivalente do `/importacoes/ultima`): ao montar a tela, se houver import não-terminal,
retoma o polling. Um parse de 2 minutos garante que o usuário vai dar F5.

### 5.4 Modelo de execução — o maior desvio da POC

A POC roda tudo dentro do processo da API com `child_process.fork()` e `ts-node`. Em EKS,
com pods recicláveis, imagem Alpine e `USER nestjs`, isso não sobrevive intacto.

**Opção 1 — `fork()` dentro do pod da API (POC ao pé da letra).**

- ✅ Menor caminho até funcionar; o código da POC quase cola.
- ❌ Import morre em rolling deploy sem deixar rastro recuperável.
- ❌ 2–8 min de CPU pesada no pod que atende requisição.
- ❌ Precisa de `ts-node` (não existe em prod) ou de resolver o caminho `.js`/`.ts` (§3.7).
- ❌ Chromium para miniatura na imagem Alpine: **não funciona**.

**Opção 2 — job no Mongo + claim atômico + `@Cron`, dentro dos pods da API.**

- ✅ **É o padrão da casa** (`webhooks-outbound`), com decisão de tech-lead já registrada.
- ✅ Sobrevive a restart: lock expira, outro pod reclama.
- ✅ Seguro com N réplicas.
- ✅ Nenhuma infraestrutura nova.
- ⚠️ CPU pesada continua no pod da API — mitigável com concorrência 1 por pod e
  `ENABLE_CRON_JOBS` só onde deve rodar.
- ❌ Ainda não resolve Chromium na imagem Alpine.

**Opção 3 — Opção 2 + Deployment de worker dedicado, com imagem própria (glibc + Chromium).**

- ✅ Correto em escala; isola CPU/memória; a imagem grande (~1,5 GB) não afeta a API.
- ✅ Permite escalar miniatura independentemente do parse.
- ❌ Custo real: novo `Dockerfile`, novo workflow de CI, novo Deployment, novo alvo de
  observabilidade, e mais uma imagem para manter.

**Opção 4 — Kubernetes `Job` por importação.** Precisa de RBAC no pod e cliente k8s.
Descartada: complexidade desproporcional.

**Recomendação: partir as duas fases.**

| Fase | Onde | Por quê |
|---|---|---|
| **Parse + geometria + produtos + publicação** | Opção 2 — cron + claim nos pods da API | Node puro, sem browser. Funciona em Alpine. Segue o padrão da casa |
| **Miniaturas** | Opção 3 — worker dedicado, imagem glibc com Chromium | Playwright não roda em Alpine. Miniatura é fire-and-forget e não bloqueia publicação, então pode ficar num segundo incremento |

Isso permite um **primeiro incremento inteiro sem Chromium**: catálogo publicado e
navegável, com o fallback de render no browser que já existe em produção (`thumbBaseUrl`
nulo). O segundo incremento acrescenta as miniaturas e a página fica rápida. **A
retrocompatibilidade do `LazyBimCard` é o que torna esse faseamento possível** — sem ela,
publicar sem miniatura não seria opção.

> **Se o tech-lead preferir não criar worker dedicado**, as alternativas para a miniatura,
> em ordem de qualidade:
> 1. Trocar a base da imagem da API para `node:24-bookworm-slim` e instalar Chromium nela.
>    Uma imagem para todo mundo, ~1,5 GB, Chromium disponível em qualquer pod. Simples, mas
>    infla o deploy da API inteira.
> 2. Usar `SIMBOLOGIA_3D.IMAGEM` — o BMP **100×100 que o AltoQi já pré-renderizou** e que
>    o `aq-reader` já extrai (`AqSimbologia.imagem`). Custo zero, sem Chromium. **Falha na
>    barra de fidelidade**: 100×100 para um card de 224×162 (448×324 em DPR 2), com câmera,
>    material e fundo do AltoQi, não do viewer. Serve como *placeholder* enquanto a
>    miniatura real não existe, não como substituto.
> 3. Não gerar miniatura e aceitar o render no browser. **É o comportamento de 39,9 s de
>    LCP.** Não recomendado, mas é o estado atual dos catálogos antigos, então não é
>    regressão.
>
> Ver §10, **D-2**.

**Regras de execução, independentes da opção escolhida:**

- **Concorrência 1 por pod** para parse. Dois parses simultâneos num pod = 2× a memória de
  pico (+422 MB medido no menor caso).
- **Timeout por job.** A POC usa 5 min para o parse (`WORKER_TIMEOUT_MS`) e mata com
  `SIGKILL`. Em produção, com Maxbar de 618 MB, meça antes de fixar; e o timeout tem que
  marcar `falhou` com mensagem, não deixar preso.
- **Lock com expiração** (`lockedAt` + `LOCK_TIMEOUT_MS`), como no `claimNextBatch`.
- **Tentativas limitadas.** Um `.aq` corrompido não pode ser reclamado para sempre:
  `attempts` + `maxAttempts` → `falhou`.
- **`ENABLE_CRON_JOBS`** na primeira linha do método `@Cron`. Em dev/hml fica `false`, então
  **preveja um caminho de disparo manual** (endpoint admin ou comando `nest-commander` —
  o projeto já usa `pnpm --filter api cli`), senão não há como testar em homologação.
- **Log estruturado com o `importId` curto** em cada transição, como a POC faz
  (`[${importId.slice(0,8)}] → parseando — +12.4s`). Com `dd-trace` já no `main.ts`, isso
  vira rastro pesquisável.

### 5.5 Storage no S3

**`S3GeometryStore`** implementa a interface de §4.1:

| Método | Implementação |
|---|---|
| `put(key, data)` | `PutObjectCommand` com `ContentType` e, para geo, `ContentEncoding: 'gzip'` |
| `get(key)` | `GetObjectCommand` → buffer |
| `stat(key)` | `HeadObjectCommand` → `{ size: ContentLength, mtimeMs: LastModified.getTime() }` |
| `delete(key)` | `DeleteObjectCommand` |
| `deleteByPrefix(prefix)` | **reusar `S3Service.deletePrefix`**, que já pagina o `ListObjectsV2` |

**Recomendação forte: chaves content-addressed.**

```
bim-3d/geo/{sha256(geoBuffer).slice(0,32)}.json.gz
bim-3d/thumb/v1/{sha256(geoBuffer).slice(0,32)}.webp
bim-imports/raw/{importId}.aq
```

Quatro ganhos de uma decisão só:

1. **`Cache-Control: public, max-age=31536000, immutable` fica correto** — a URL muda
   quando o conteúdo muda. É o que S6.1 apontou como o padrão certo com CDN na frente, e
   que a POC não pôde fazer.
2. **Dedup de geometria e de miniatura de graça.** Amanco: 856 produtos → **448 objetos**,
   porque 448 geometrias distintas. Metade do trabalho de miniatura desaparece.
3. **Reimportar o mesmo `.aq` não reescreve nada** — as chaves coincidem. Reimportação
   passa a ser barata.
4. **Cross-catálogo:** peças iguais em bibliotecas diferentes compartilham objeto.

**O `v1` na chave da miniatura não é decoração.** Se o renderizador mudar (versão do
Three.js, luz, câmera), a mesma geometria produz imagem diferente — e com chave só por
conteúdo da geometria, a imagem nova nunca seria buscada. Versione o **renderizador** na
chave e guarde essa versão no documento de produto/import.

**Como o browser busca cada coisa:**

| Asset | Caminho recomendado | Por quê |
|---|---|---|
| Miniatura | **direto no CloudFront** (`<img src>`) | `<img>` não passa por CORS. É o que o B-17 já faz. Passar pela API custaria cache de CDN sem resolver nada |
| Geometria | **direto no CloudFront**, com CORS configurado no bucket/distribuição | `fetch()` **passa** por CORS, e foi por isso que o B-18 criou o proxy. Com `Access-Control-Allow-Origin` configurado na origem, o proxy deixa de ser necessário — e a geometria volta para o CDN com gzip, o que o proxy tirou |
| Geometria (fallback) | proxy existente `GET b-bim-3d/:customLink/:slug/geo/:filename` | Se configurar CORS no bucket não for viável no prazo, mantenha o proxy — mas então **acrescente compressão**, porque hoje ele serve sem (`transfer 1.765 KB / resource 1.763 KB` medido) |

> A rota de geometria do proxy é `.../geo/:filename` e valida
> `^[a-z0-9][a-z0-9\-_.]{0,100}\.json$` **antes de tocar no storage**. Chave
> content-addressed (hex de 32 chars + `.json`) passa nessa regex. Se a extensão virar
> `.json.gz`, a regex **rejeita** — ajuste as duas coisas juntas.

**Compressão da geometria: faça no primeiro incremento.** Razão medida **5,8×**; pior caso
de página cai de 40 MB para ~7 MB. É `zlib.gzipSync(buffer)` + `ContentEncoding: 'gzip'` no
`put`. O CloudFront entrega e o browser descomprime transparentemente. O B-17 registrou
isso como "melhoria conhecida" não implementada para não ampliar escopo; aqui é escopo.

### 5.6 Modelo de dados e coexistência com o ZIP

**O conflito, concreto:** `bim_catalogs.catalogUrl` e `.geoBaseUrl` são `required: true`.
Um catálogo gerado do `.aq` não tem `catalog.json` nem um `geoBaseUrl` único (as chaves são
por conteúdo).

**Opções:**

| Opção | Prós | Contras |
|---|---|---|
| **A. Estender `bim_catalogs`** com `source: 'zip' \| 'aq'` e tornar `catalogUrl`/`geoBaseUrl` opcionais | Uma coleção, um índice, uma página pública, um admin. O `resolveFields()` já é o precedente de lidar com formas diferentes | Documento com campos que só valem para um dos `source`; validação por `source` no service |
| B. Coleção nova `bim_dynamic_catalogs` | Isolamento total | Duas listagens, duas rotas públicas, duas telas de admin, dois caminhos de delete. A URL pública `/{customLink}/{slug}` teria de consultar as duas |

**Recomendação: A.** Com regras explícitas:

```typescript
@Prop({ type: String, enum: ['zip', 'aq'], default: 'zip', required: true })
source: 'zip' | 'aq'

@Prop({ type: String, default: null })  catalogUrl?: string    // required só quando source==='zip'
@Prop({ type: String, default: null })  geoBaseUrl?: string    // idem
@Prop({ type: String, default: null })  thumbBaseUrl?: string
```

- `default: 'zip'` faz os **9 catálogos existentes continuarem válidos sem migração**.
- A obrigatoriedade migra do schema para o service, por `source`. Isso é uma **quebra de
  invariante no banco** e precisa estar explícita no PR e no doc do módulo.
- Todo consumidor que hoje lê `catalogUrl` sem checar precisa passar a checar `source`.
  Hoje são: `getCatalogJson()`, `getGeoJson()` (service), `getBimCatalogData` (web,
  `queries/bim-catalog.ts`) e a interface `BimCatalog` do admin (`queries/bim-catalog.ts`).

**Coleção `bim_products` (nova).** Baseada na POC, com nomes em inglês:

```typescript
@Schema({ collection: 'bim_products', timestamps: true })
export class BimProduct {
  @Prop({ type: String, default: uuidv4 })      _id: string        // uuid, não ObjectId — sem enumeração por adivinhação
  @Prop({ required: true })                     catalogId: string
  @Prop({ required: true })                     importId: string   // permite trocar o lote inteiro
  @Prop({ required: true })                     slug: string       // id do produto dentro do catálogo
  @Prop({ required: true })                     name: string
  @Prop()                                       series: string
  @Prop({ type: MongooseSchema.Types.Mixed })   specs: Record<string, string>
  @Prop({ type: [[Number]], default: null })    curve: number[][] | null   // [[Q,H,P,eff]]
  @Prop()                                       power: number
  @Prop({ required: true })                     geoKey: string
  @Prop()                                       thumbKey: string
  @Prop({ type: Date, default: null })          deletedAt?: Date   // convenção da casa
}
BimProductSchema.index({ catalogId: 1 })
BimProductSchema.index({ catalogId: 1, series: 1 })
BimProductSchema.index({ importId: 1 })
```

Notas de modelagem, à luz das regras de `bilds.com/CLAUDE.md`:

- **Referência, não embed.** A regra da casa manda embutir 1:N com N < ~100. Amanco tem
  856 produtos e um `specs` livre — passa do teto e cresce sem limite. Coleção separada é
  o certo, e a POC provou.
- `specs` como `Mixed` é inevitável (chaves livres vindas do `.aq`). Documente que **não é
  indexável** e que filtro por spec, se um dia for requisito, precisa de outro desenho.
- `deletedAt` porque é convenção. Mas note a tensão: o catálogo pai usa hard delete
  (KTD-5). **Recomendação:** produto acompanha o catálogo — quando o catálogo é apagado, os
  produtos vão com ele por hard delete, e o `deletedAt` fica para remoção individual de
  produto (que não existe no primeiro incremento). Decida e escreva no doc; um review vai
  perguntar.

**Coleção `bim_imports` (nova).** A da POC (§4.6) mais os contadores de §5.3 mais o que a
produção exige:

```typescript
_id, companyId, catalogId?, status, phase?, error?, note?,
fileName, fileSize, sourceKey,          // chave do .aq bruto no S3
sourceHash,                             // sha256 — dedup e rastreio
pipelineVersion,                        // qual versão do parser gerou (reprocessamento)
productsTotal?, productsDone?, thumbsTotal?, thumbsDone?, skippedNoGeometry?,
attempts, maxAttempts, lockedAt?, nextAttemptAt,   // claim atômico (§3.6)
createdBy,                              // profileId de quem subiu — auditoria
startedAt?, finishedAt?, createdAt, updatedAt, deletedAt
```

Índices: `{ companyId, createdAt: -1 }` (última importação), `{ status, nextAttemptAt }`
(claim), `{ sourceHash }` (dedup).

### 5.7 Visibilidade e publicação

**Isto é requisito, não hardening.** Hoje, `bim_catalogs` **não tem campo de
visibilidade**, e `BimCatalogRepository.findByCustomLinkAndSlug` filtra só por
`{ companyCustomLink, slug, deletedAt: null, active: true }`
— ou seja, **o catálogo fica público no instante em que existe**. Na POC isso era
aceitável (um usuário, dados descartáveis). Aqui não: o fabricante sobe o arquivo dele e o
catálogo aparece na web sem revisão.

A pendência está registrada nos dois lados: `bilds-bim-3d/CLAUDE.md` ("Pendência
conhecida") e `docs/sessoes/S6.1-cache-de-assets.md` §6, que a classifica explicitamente
como **requisito para a bilds.com**.

> Nota importante do mesmo registro, para não reintroduzir um achado inválido: a antiga
> finding "GET /geometrias sem auth — adicionar guard" **é inaplicável**. Um `AuthGuard` na
> rota de geometria quebra a página pública, porque é o viewer no browser do **visitante**
> que busca a geometria, sem token. E o `_id` é `crypto.randomUUID()`, então não há
> enumeração por adivinhação. O controle correto é **visibilidade do catálogo**, não auth
> no asset.

**Recomendação:**

```typescript
@Prop({ type: String, enum: ['draft', 'published'], default: 'draft', required: true })
visibility: 'draft' | 'published'
```

- Import bem-sucedido cria/atualiza o catálogo como **`draft`**.
- Fabricante (ou admin) publica explicitamente: `PATCH .../b-bim-3d/:slug/visibility`.
- Rotas públicas filtram `visibility: 'published'`.
- **Os 9 catálogos existentes precisam de `visibility: 'published'`** — `default: 'draft'`
  os esconderia. Duas saídas: default `'published'` (retrocompatível, menos seguro para o
  fluxo novo) ou default `'draft'` + **script de backfill** nos existentes. **Recomendo
  default `'draft'` + backfill**, e o backfill como comando `nest-commander` no PR
  (o projeto já tem `devops/scripts/` e `pnpm --filter api cli` para isso).
- Reimportar um catálogo publicado **não deve despublicá-lo** — a troca de produtos é in
  place. Escreva o teste dessa regra.

### 5.8 Autorização e limites

| Item | Recomendação |
|---|---|
| Quem sobe | `@VerifySession()` + `assertPermission(companyId, userId)` — reuso literal. Cobre criador, administradores e admin Bilds (bypass do KTD-10) |
| Fabricante | Considerar exigir `company.partner === true` para o fluxo self-service (é o filtro do portal). **Decisão de produto** — §10, **D-5** |
| `customLink` | Rejeitar empresa sem `customLink`, como `uploadCatalog` já faz — sem ele não há URL pública |
| Rate limit | Endpoint de upload **precisa** de `@Throttle` próprio: é 800 MB e minutos de CPU por chamada. O global de 100 req/min não protege nada aqui. Sugestão: 3 req / 10 min por usuário |
| Concorrência por empresa | Recusar novo import enquanto houver um não-terminal para a mesma empresa (`409 Conflict`). Evita dois parses do mesmo catálogo brigando pelo upsert |
| Validação de conteúdo | Extensão + magic bytes: `.aq` é `SQLite format 3\0` **ou** `PK` (ZIP). O `file-type` reconhece as duas assinaturas (`sqlite` e `zip`), então a regra pode ser estrita, **sem** `trustExtensionWhenUndetected`: `aq: { detectedExts: ['sqlite', 'zip'] }`. **Confirme com fixture real dos dois formatos** — a lista de assinaturas do `file-type` muda entre versões |
| Tamanho | `fileSize` no Multer (~800 MB, folga sobre os 618 MB do Maxbar) e limite de `productCount`/`entries` para blindar `.aq` hostil |
| Robustez do parser | Manter os guards do `oq3d-parser` que validam contagem declarada **antes** de alocar. O `.aq` agora é entrada de usuário |
| SSRF | Se o DTO de import receber `fileUrl` (Opção A de §5.2), **valide o host contra `AWS_CLOUD_FRONT_BASE_URL`**. `@IsUrl()` sozinho aceita `http://169.254.169.254/...` |
| CSRF | Nada a fazer: o guard é opt-in por `@RequireCSRF()` e ninguém usa |

### 5.9 O lado consumidor — página pública

O que **não** muda: `LazyBimCard`, `BimViewer`, `CurveChart`, `ProductModal`,
`CatalogGridLayout`, `SeriesRowsLayout`, `buildCatalogJsonLd`, os dois layouts, o
`object-contain` da miniatura, o `h2` obrigatório da seção de produtos (B-16d), a
hierarquia de headings, o `error.tsx`/`loading.tsx` da rota.

O que muda: **de onde vêm os produtos**.

Hoje: `BimCatalog.tsx` faz duas queries (`meta` e `catalogData`), a segunda buscando o
`catalog.json` inteiro pelo proxy. Para `source: 'aq'`, os produtos vêm do banco.

**Recomendação:** um endpoint público que devolve a mesma **forma** que o
`BimCatalogData` já tem, para não tocar em nenhum componente de apresentação:

```
GET b-bim-3d/:customLink/:slug/products?series=&page=&limit=
→ { slug, titulo, fabricante, descricao, layout, filtros, produtos: [...] }
```

Onde cada produto traz `geo` e `thumb` como **URL absoluta** (CloudFront), em vez de nome
de arquivo. Duas formas de fazer isso sem quebrar o legado:

1. Manter os nomes de campo em PT que `types.ts` já espera e mapear no backend. **Menor
   diff, zero risco no frontend.** Feio, mas honesto: é o formato que o consumidor já tem.
2. Padronizar em EN e ajustar `types.ts` + os cinco componentes. Mais limpo, mais diff,
   mais chance de repetir o B-15 (campos vazios silenciosamente).

**Recomendo (1) no primeiro incremento**, com nota explícita de dívida. E como
`BimCatalogView` recebe `geoBaseUrl`/`thumbBaseUrl` por prop, URLs absolutas por produto
exigem um ajuste pequeno: `geoBaseUrl=''` e `produto.geo` já absoluto funciona sem tocar em
lógica de concatenação.

**Dois pontos de performance que o novo caminho deve resolver, não herdar:**

- **CLS 0,971.** `BimCatalog.tsx` devolve `null` enquanto o RTK Query busca, e o footer é
  empurrado quando a grade monta. É o item pendente do BILDS-550 e **não é resolvido por
  miniatura**. Com produtos no banco, o SSR pode renderizar a primeira dobra: reserve
  espaço com skeleton (`animate-pulse`) na altura final, ou renderize a grade no servidor.
- **Cache da página.** O aprendizado da POC: `Cache-Control: public, max-age=300,
  stale-while-revalidate=60` (ou equivalente) na página faz o CDN cachear o HTML do SSR e o
  TTFB converge com o modelo estático. Sem isso, SSR é 3–6× mais lento que o edge.

**Paginação passa a ser possível — e é o ganho de produto.** 856 produtos hoje descem num
JSON só. Com banco, `?series=&page=&limit=` é natural. **Mas cuidado com SEO:** o
`ItemList` do JSON-LD enumera **todos** os produtos e `numberOfItems` tem que bater com
`itemListElement.length` (foi o bug B-16, com teste de regressão em
`buildCatalogJsonLd.test.ts`). Se a página paginar, o JSON-LD precisa continuar enumerando
tudo — ou seja, o `generateMetadata`/JSON-LD precisa de uma consulta própria, sem
paginação, projetando só os campos que ele usa.

---

## 6. Contratos propostos

Proposta, não imposição — mas se mudar, mude com motivo escrito.

### 6.1 Endpoints

| Método | Rota | Auth | Corpo / Query | Resposta |
|---|---|---|---|---|
| POST | `companies/:id/bim-imports/upload` | `@VerifySession()` + `assertPermission` + `@Throttle` | multipart, campo `file` (`.aq`) | `201 { importId, status, url }` |
| POST | `companies/:id/bim-imports` | idem | `{ fileUrl }` (só se adotada a Opção A de §5.2) | `201 { importId, status }` |
| GET | `companies/:id/bim-imports/latest` | idem | — | `200 ImportStatusDto \| null` |
| GET | `companies/:id/bim-imports/:importId` | idem | — | `200 ImportStatusDto` |
| POST | `companies/:id/bim-imports/:importId/retry` | idem | — | `202 { importId, status }` |
| PATCH | `companies/:id/b-bim-3d/:slug/visibility` | idem | `{ visibility }` | `200 BimCatalog` |
| GET | `b-bim-3d/:customLink/:slug/products` | `@PublicAccess()` | `?series=&page=&limit=` | `200 BimCatalogData` |

> **KTD-3 outra vez:** `b-bim-3d/:customLink/:slug/products` é segmento fixo depois de dois
> dinâmicos — precisa ser declarado **antes** de `b-bim-3d/:customLink/:slug`, junto de
> `/catalog` e `/geo/:filename`. E `companies/:id/bim-imports/latest` **antes** de
> `companies/:id/bim-imports/:importId`, senão `"latest"` é lido como `importId` (a POC
> tinha o mesmo cuidado com `/ultima`).

### 6.2 Status e fases

```typescript
export const BIM_IMPORT_STATUSES = [
  'recebido',    // objeto no S3, job enfileirado
  'parseando',   // worker leu o .aq, extraindo geometria
  'gravando',    // produtos e catálogo para o MongoDB
  'publicado',   // catálogo utilizável (miniaturas podem estar pendentes)
  'vazio',       // arquivo válido, nenhuma peça com geometria 3D — NÃO é erro
  'falhou',
] as const
```

Miniatura **não** é status: é `thumbsDone/thumbsTotal` sobre `publicado`. Se virar status,
uma falha de Chromium passa a "reprovar" um catálogo que está bom.

**DTO de status** (o que a UI consome):

```typescript
export class ImportStatusDto {
  importId: string
  status: BimImportStatus
  phase?: string
  productsTotal?: number
  productsDone?: number
  thumbsTotal?: number
  thumbsDone?: number
  skippedNoGeometry?: number
  productCount?: number
  catalogId?: string | null
  catalogSlug?: string | null       // para o link "ver catálogo"
  error?: string | null
  note?: string | null
  startedAt?: string | null
  finishedAt?: string | null
  createdAt: string
  updatedAt?: string | null
}
```

### 6.3 Erros

| Situação | Status | Mensagem (i18n no front) |
|---|---|---|
| Arquivo ausente | 400 | `bim3d.import.error.fileRequired` |
| Extensão/conteúdo inválido | 400 | `bim3d.import.error.invalidFile` |
| Acima do limite | 413 | `bim3d.import.error.tooLarge` |
| Empresa sem `customLink` | 400 | `bim3d.import.error.noCustomLink` |
| Sem permissão | 403 | `bim3d.import.error.forbidden` |
| Empresa ou import inexistente | 404 | `bim3d.import.error.notFound` |
| Import em andamento para a empresa | 409 | `bim3d.import.error.alreadyRunning` |
| Rate limit | 429 | `bim3d.import.error.tooManyRequests` |

Mensagem técnica de falha do parse vai em `import.error` (para o admin ver), **nunca** com
stack. A UI mostra texto traduzido; o detalhe fica num bloco secundário, como a POC faz.

### 6.4 i18n

Chaves novas em **pt, en, es**, sob o prefixo já usado (`bim3d.*` no web,
`bim3d.admin.*` no admin). Mínimo:

```
bim3d.import.title            bim3d.import.dropZone           bim3d.import.selectFile
bim3d.import.fileRequirements bim3d.import.uploading          bim3d.import.processing
bim3d.import.step.received    bim3d.import.step.parsing       bim3d.import.step.saving
bim3d.import.step.published   bim3d.import.emptyTitle         bim3d.import.emptyBody
bim3d.import.failedTitle      bim3d.import.retry              bim3d.import.uploadAnother
bim3d.import.productsProgress bim3d.import.thumbsProgress     bim3d.import.elapsed
bim3d.import.skippedNoGeometry
bim3d.import.error.*  (a tabela de §6.3)
bim3d.catalog.visibility.draft  bim3d.catalog.visibility.published  bim3d.catalog.publish
```

Textos com contagem precisam de plural (`_one`/`_other`) — o admin já usa esse padrão
(`bim3d.admin.catalogsCount_one/other`).

### 6.5 RTK Query

```typescript
// apps/web/src/queries/bim-import.ts
const TAG = 'BimImport' as const     // ← REGISTRAR em queries/index.ts tagTypes

startBimImport   : mutation  // multipart; usa MediaUploader, não este hook, para o arquivo
getBimImport     : query     // { companyId, importId } — pollingInterval no consumidor
getLatestBimImport: query    // { companyId }
retryBimImport   : mutation  // invalida { type: TAG, id: importId }
publishBimCatalog: mutation  // invalida 'BimCatalog' + { type:'BimCatalog', id: companyId }
```

Duas armadilhas de RTK Query já registradas no módulo:

- **Multipart:** se algum dia esta camada postar o arquivo, use `queryFn` (não `query`) e
  `headers: { 'Content-Type': undefined }` — senão o RTK define `application/json` e o
  boundary do multipart se perde. É o que `apps/admin/src/queries/bim-catalog.ts` faz e
  documenta.
- **Tag nova sem registro em `queries/index.ts`** quebra o build de TypeScript.

---

## 7. Armadilhas — tabela consolidada

Cada linha é um erro já cometido por alguém, com a consequência observada. Esta seção
existe para que o `code-review` posterior tenha o que conferir.

### 7.1 Formato e parse do `.aq`

| # | Armadilha | Consequência |
|---|---|---|
| A-1 | Ler texto como latin-1 (ou UTF-8) em vez de **cp1252** | Travessão, aspas curvas e reticências viram bytes crus na página pública. **Silencioso** — latin-1 nunca lança |
| A-2 | Trocar `text_factory`/decoder sem `CAST(... AS BLOB)` nas colunas binárias | O round-trip de cp1252 não é reversível: corrompe a malha 3D em silêncio |
| A-3 | `SELECT *` em `SIMBOLOGIA_3D` | Traz `WIREFRAME`: **69–71% do arquivo** (285 MB dos 412 MB da Amanco), inútil para web. Triplica a memória do parse |
| A-4 | Ler a rotação de `TCoordinateTransformation3D` como row-major | Ela é **column-major**. Sai transposta: peça fora de lugar, **sem mudar a contagem de triângulos** — passa despercebido |
| A-5 | Ignorar `TQi3DReusedObject` que referencia a definição | Perde **~31% dos triângulos** na Amanco. A referência é o **índice de serialização base 1**, não o GUID (que é único por instância) |
| A-6 | Ancorar a varredura no byte anterior ao `0x5B` | O byte que precede varia. Ancore só no `0x5B` |
| A-7 | Varrer delimitadores byte a byte | `0x5B`/`0x5D` ocorrem dentro de doubles. Consuma blocos de tamanho conhecido por inteiro antes de varrer |
| A-8 | Esquecer o fator `0.01` (cm → m) | Modelo **100× maior** |
| A-9 | Trocar os eixos errado | É `x→x, z→y, -y→z`. Errado: peça deitada ou espelhada |
| A-10 | Somar cores de marcador na bounding box | Verde `(1,154,63)`, azul `(10,84,152)`, `(0,116,232)` são bocais, não produto. Inflam a bbox (~2 cm) e **mudam o enquadramento da miniatura** |
| A-11 | Não dedupar | Geometria **4× maior** (182,7 MB × 44,7 MB no Dancor) |
| A-12 | Dedupar só por posição, sem cor | Vértices coincidentes com cores diferentes se fundem: o logo branco sobre corpo vermelho perde a cor |
| A-13 | Tratar "peça sem geometria" como erro | 27% das peças da Amanco (312 de 1.168) são tubos e kits sem forma fixa. É o comportamento **esperado** |

### 7.2 Runtime, memória e processo

| # | Armadilha | Consequência |
|---|---|---|
| A-14 | `memoryStorage` do Multer para o `.aq` | 618 MB de `Buffer` no pod, por upload concorrente. Use `diskStorage` |
| A-15 | Esquecer o disco efêmero | `.aq` em ZIP escreve **uma segunda cópia** em `/tmp`. Até ~2× o tamanho do arquivo. Sem `ephemeral-storage` declarado, o pod é evictado |
| A-16 | `process.send!(result); process.exit(0)` | O IPC não faz flush e **a mensagem é perdida**. Só aparece em payload grande: com 13 produtos funcionava; com 856 o import ficava preso em `parseando` até o timeout. Use `process.send!(result, () => process.exit(0))` |
| A-17 | `fork()` com caminho `.ts` e `ts-node` no `execArgv` | Funciona em dev, **quebra em produção** (`dist/src/main.js`, sem ts-node) |
| A-18 | Trabalho longo em fire-and-forget dentro do pod | Rolling deploy mata o import sem rastro. Use job no banco com claim e lock expirável |
| A-19 | Cron sem `ENABLE_CRON_JOBS` | Reprova em review, e roda em dev/hml onde não deve |
| A-20 | Cron sem claim atômico com N réplicas | O mesmo import é processado por vários pods |
| A-21 | Dois parses concorrentes no mesmo pod | 2× a memória de pico (+422 MB já no menor caso) |
| A-22 | Não limpar no `falhou` | Geometria órfã no S3, produtos órfãos no Mongo. Pague `deleteByPrefix` + `deleteMany` |

### 7.3 Miniaturas

| # | Armadilha | Consequência |
|---|---|---|
| A-23 | Rasterizar fora do Three.js | 27 dB × 47 dB de PSNR contra o viewer. O catálogo passa a ter **dois visuais** conforme o produto tenha ou não miniatura pronta. Recusado pelo dono do produto |
| A-24 | Passar a geometria como **objeto** para `page.evaluate` | ~2.200 ms × ~370 ms por peça. Lote de 13: 24,5 s × 6,2 s. Passe **string JSON** e parseie dentro da página |
| A-25 | Subir um browser por miniatura | ~1 s de startup por item em vez de por lote |
| A-26 | `process.exit()` sem fechar o browser | Chromium órfão; o handle do servidor HTTP prende o exit |
| A-27 | Servir o harness por `file://` | O Chromium recusa `import` de módulo ES sobre `file://`. Sirva por HTTP efêmero (`listen(0)`) |
| A-28 | Playwright em imagem Alpine | Não é suportado (musl). `pnpm install --ignore-scripts` também não baixa o browser |
| A-29 | Esquecer `--no-sandbox` / SwiftShader | Sem GPU e sem privilégio de namespace, o WebGL headless não inicializa |
| A-30 | Divergir o `buildScene()`/câmera do harness em relação ao viewer | Miniatura deixa de casar com o 3D. Os dois `buildScene()` são idênticos hoje **de propósito** — mexa nos dois juntos |
| A-31 | `object-fit: fill` na miniatura | A peça estica em card largo. A imagem é 448×324 fixo; use `object-contain` (a sobra tem a cor do card) |
| A-32 | Uma miniatura por produto em vez de por geometria | ~48% de trabalho desperdiçado na Amanco (856 produtos, 448 geometrias) |
| A-33 | Chave de miniatura sem versão do renderizador | Trocar o renderizador não invalida a imagem: CDN serve a velha para sempre |

### 7.4 API, cache e rotas

| # | Armadilha | Consequência |
|---|---|---|
| A-34 | Declarar segmento fixo depois de dinâmico no controller | `"summary"`/`"latest"`/`"products"` é lido como parâmetro. Silencioso, compila (KTD-3) |
| A-35 | `Cache-Control: immutable` com chave derivada do import | Regenerar a miniatura na mesma chave nunca chega ao browser. Ou content-addressed + `immutable`, ou `must-revalidate` + ETag por conteúdo |
| A-36 | ETag derivada só da chave | Não muda quando os bytes mudam. Inclua `size`+`mtime` (ou hash do conteúdo/ETag do S3) |
| A-37 | Ler o blob antes de decidir o 304 | A geometria de MBs sai do storage à toa. Decida com `stat`/`HeadObject` primeiro |
| A-38 | Servir geometria sem compressão | Razão medida 1,00× onde poderia ser 5,8×. Foi parte do LCP de 39,9 s |
| A-39 | `@IsEnum(['a','b'])` em array literal | Aceita `'0'`, `'1'` como válidos. Use `@IsIn(ARRAY)` |
| A-40 | `@Session('userId')` em endpoint `@PublicAccess()` | Erro "Session does not exist" para anônimo. Use `@OptionalUserId()` |
| A-41 | Esquecer `EnvService` nos `providers` do módulo | `UnknownDependenciesException` no startup (KTD-6) |
| A-42 | `process.env.X` direto | Reprova em review; e a var não é validada |
| A-43 | `@IsUrl()` sem allowlist de host num DTO que recebe URL | SSRF: `http://169.254.169.254/latest/meta-data/` |
| A-44 | Tornar `catalogUrl` opcional sem checar `source` nos consumidores | `getCatalogJson`, `getGeoJson`, `getBimCatalogData` e a interface do admin quebram com `undefined` |
| A-45 | Publicar catálogo sem visibilidade | Fica público no instante em que existe |
| A-46 | Adicionar `AuthGuard` na rota de geometria | Quebra a página pública: quem busca é o browser do visitante, sem token |

### 7.5 Frontend

| # | Armadilha | Consequência |
|---|---|---|
| A-47 | Prop `allowedTypes` no `MediaUploader` | Não existe. É `acceptType` (string por vírgula) + `allowedExtensions` (array) |
| A-48 | Reimplementar barra de progresso de upload | Já existe: `MediaItem.progress` via `xhr.upload.onprogress` em `queries/medias.ts` |
| A-49 | Texto hardcoded | Reprova. Três locales, sempre, inclusive rótulo de passo e mensagem de erro |
| A-50 | `style={{}}` inline | Reprova. (A UI da POC e o admin do BIM 3D estão cheios — é dívida, não licença) |
| A-51 | Tag nova em `queries/` sem registrar em `queries/index.ts` | Quebra o build de TypeScript |
| A-52 | Multipart via RTK `query` em vez de `queryFn` | RTK define `Content-Type: application/json` e o boundary se perde |
| A-53 | Campos PT × EN | Bug B-15: cards com título/fabricante vazios. `catalog.json` é PT, `bim_catalogs` é EN |
| A-54 | Container devolver `null` enquanto carrega | CLS 0,971 medido: o footer é empurrado quando a grade monta. Use skeleton com a altura final |
| A-55 | Paginar produtos e paginar o JSON-LD junto | `numberOfItems` deixa de bater com `itemListElement` (B-16, com teste de regressão) |
| A-56 | Investigar 404 de catálogo novo no código | Em dev, geralmente é cache do Next. Confira `curl` na API primeiro (as três rotas), depois force recompilação |

### 7.6 Testes

| # | Armadilha | Consequência |
|---|---|---|
| A-57 | Testar upload sem mockar `resolveContentType` | O util carrega o pacote ESM `file-type` via `load-esm`, que o Jest em CJS não importa. Todo teste que alcança o bloco de upload falha com "Erro ao enviar arquivos para o S3", **mascarando a causa real**. Mock: `jest.mock('@/common/utils/file-type-detector.util', () => ({ resolveContentType: jest.fn().mockResolvedValue('application/json') }))` |
| A-58 | Comparar geometria entre implementações com `===` | `-0.0` × `0.0` em vértices no plano y=0. Use comparador semântico com tolerância (~10 µm) |
| A-59 | Validar parser só pela bounding box | Uma rotação e sua transposta podem gerar **a mesma caixa**. Compare o conjunto de pontos, alinhando pelo **canto** da bbox (não pelo centróide: o OQ3D guarda sopa de triângulos, o IFC solda vértices — pesos diferentes) |

---

## 8. Plano de implementação sugerido

Quatro incrementos, cada um mergeável e verificável. Vira plano com pouca adaptação.

### Incremento 0 — Decisões e fundação (sem feature visível)

**Entregas:** decisões de §10 fechadas e registradas; `visibility` no schema + backfill dos
9 catálogos; `source` no schema com `catalogUrl`/`geoBaseUrl` opcionais e validação por
`source` no service; `bim_products` e `bim_imports` criados; `IGeometryStore` +
`S3GeometryStore` + `DiskGeometryStore` + provider por `BIM_STORAGE`; métodos aditivos no
`S3Service` (`headObject`, `uploadStream`, `downloadToFile`, `ContentEncoding`); correções
de doc de §3.2.

**Aceite:** os 9 catálogos existentes continuam respondendo 200 nas páginas públicas; suíte
de `b-bim-3d` verde; smoke do `S3GeometryStore` (put/get/stat/delete/deleteByPrefix) contra
um bucket de dev.

### Incremento 1 — Pipeline até catálogo publicado, sem miniatura

**Entregas:** `lib/aq-reader.ts`, `lib/oq3d-parser.ts`, `lib/dedup-buffers.ts` portados com
teste unitário sobre fixture real; endpoint de upload autenticado com `diskStorage` → S3;
`bim_imports` com claim atômico + `@Cron` processor; parse → geo (gzip, chave
content-addressed) → `bim_products` → upsert de `bim_catalogs` com `source: 'aq'` e
`visibility: 'draft'`; endpoint público de produtos; ajuste mínimo no consumidor (§5.9);
tela de upload + progresso (web e/ou admin) com i18n nos três locales; `PATCH .../visibility`.

**Aceite:**

- Subir o `.aq` da Dancor gera catálogo com **13 produtos**.
- A peça `2cv-t-220-380v-inc-flg-ir3` tem **27.425 triângulos** (com parser correto; 20.452
  indica parser antigo).
- Dedup ativo: geometria total da Dancor ~44,7 MB, **não** ~182,7 MB.
- A página pública renderiza com o fallback de render no browser (sem `thumbBaseUrl`).
- Um F5 no meio do parse retoma o progresso.
- `falhou` limpa geo e produtos.
- Biblioteca sem geometria termina em `vazio`, não `falhou`.

### Incremento 2 — Miniaturas fiéis

**Entregas:** o modelo de execução decidido em **D-2** (worker dedicado com imagem glibc +
Chromium, ou base da API trocada); harness servido por HTTP efêmero, com o **mesmo
`three@0.185.1`** do web; um browser por processo + fila; geometria como string JSON;
`closeThumbRenderer` no shutdown; chave `thumb/v1/{geoHash}.webp`; `thumbsDone/Total` no
documento de import; `thumbBaseUrl`/`thumbKey` gravados; rota de regeneração
(precedente: `bilds-bim-3d/www/tools/regen-thumbs.ts`).

**Aceite:**

- Miniatura 448×324 WebP, fundo `#F3F4F6`, ~4 KB.
- **PSNR ≥ 45 dB** contra um render do viewer na mesma câmera e tamanho (o piso do WebP
  q=0,85 é ~47 dB; 27 dB é o rasterizador software recusado).
- Página pública: **zero** requisição a geometria e **zero** `<canvas>` no carregamento.
- Falha de miniatura **não** muda o status do import.
- Regeneração invalida o cache do browser (a ETag/URL muda).

### Incremento 3 — Desempenho, robustez e o resto dos obrigatórios

**Entregas:** `Cache-Control` na página para o CDN cachear o SSR; SSR/skeleton da primeira
dobra para matar o CLS; CORS no bucket para tirar a geometria do proxy (ou compressão no
proxy); rota de reprocessamento de import (usando o `.aq` guardado); rate limit no upload;
409 de import concorrente; lifecycle rule do `bim-imports/raw/`; auditoria (`createdBy` no
import); LCP medido com **Lighthouse real**.

**Aceite:** LCP medido em produção, com número registrado no doc do módulo; CLS < 0,1;
geometria servida comprimida (razão ~5,8×); reprocessar um import antigo produz geometria
dedupada sem novo upload.

---

## 9. Como verificar

### 9.1 Testes automatizados a escrever

| Alvo | Arquivo | Cobrir |
|---|---|---|
| `lib/aq-reader` | `aq-reader.spec.ts` | cp1252 (fixture com 0x96/0x93/0x94); SQLite direto e ZIP; ausência de tabelas de bomba; peça sem `PECA_SIMBOLOGIA_3D` |
| `lib/oq3d-parser` | `oq3d-parser.spec.ts` | blob sem assinatura → `OQ3DError`; contagem declarada > buffer → erro **sem alocar**; rotação column-major (fixture com instância rotacionada); referência por índice de serialização; `skipMarkers` |
| `lib/dedup-buffers` | `dedup-buffers.spec.ts` | redução esperada; **cor na chave** (dois vértices coincidentes com cores diferentes sobrevivem) |
| `S3GeometryStore` | `s3-geometry-store.spec.ts` | chave com `../` rejeitada; `stat` mapeia `HeadObject`; `deleteByPrefix` pagina |
| `BimImportRepository` | `bim-import.repository.spec.ts` | claim atômico não entrega o mesmo doc duas vezes; lock expirado é reclamado; `attempts` respeita `maxAttempts` |
| `BimImportService` | `bim-import.service.spec.ts` | `assertPermission` (admin bypass, não-dono, empresa inexistente); 409 de concorrente; empresa sem `customLink` |
| `BimImportProcessorService` | `...processor.spec.ts` | trava `ENABLE_CRON_JOBS`; transições; `vazio`; cleanup no `falhou`; upsert substituindo import anterior; publicação **não** volta para draft |
| Controller | `bim-import.controller.spec.ts` | sem arquivo → 400; extensão inválida → 400; ordem de rota (`latest` não cai em `:importId`) |
| Público | `bim-catalog.controller.spec.ts` (estender) | `visibility: 'draft'` não aparece; `source: 'aq'` sem `catalogUrl` não quebra; ordem `products`/`catalog`/`geo` antes de `:slug` |
| JSON-LD | `buildCatalogJsonLd.test.ts` (existente) | manter as guardas de B-16 com produtos vindos do banco |

**Mock obrigatório** em qualquer teste que atravesse upload: `resolveContentType` (A-57).

### 9.2 Verificação manual — comandos

Local, com `BIM_STORAGE=local`:

```bash
# API precisa estar de pé; a porta é API_SERVER_PORT (3333)
curl -s localhost:3333/b-bim-3d/<customLink>/<slug>            | head -c 400   # meta
curl -s "localhost:3333/b-bim-3d/<customLink>/<slug>/products?limit=3" | head -c 600
curl -sI localhost:3333/b-bim-3d/files/<customLink>/<slug>/thumbs/<f>.webp     # content-type
```

Contagem de triângulos de uma geometria gravada (a conferência canônica da POC):

```bash
node -e "const g=require('./<geo>.json');console.log(g.idx.length/3)"
# CAM-W21 2CV: 27425 = parser correto | 20452 = parser antigo
```

Cache condicional (o que S6.1 validou):

```bash
E=$(curl -sI <url-geo> | awk -F': ' '/[Ee][Tt]ag/{print $2}' | tr -d '\r')
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' -H "If-None-Match: $E" <url-geo>
# esperado: 304 0
```

Progresso, ponta a ponta: subir o `.aq`, e enquanto processa
`watch -n2 'curl -s .../bim-imports/latest'` — os contadores devem avançar, não pular de 0
para o fim.

### 9.3 Alvos numéricos

| Sinal | Alvo | Origem |
|---|---|---|
| Triângulos CAM-W21 2CV | 27.425 | baseline da POC |
| Geometria Dancor (13 produtos, dedup) | ~44,7 MB | S5.1/S5.2 |
| Redução de vértices por dedup | ~80% | medido |
| Miniatura | 448×324 WebP, ~4 KB, PSNR ≥ 45 dB | ADR-004 |
| Lote de 13 miniaturas | ~6–7 s (um browser reaproveitado) | S4.4 |
| Parse de 13 produtos | ~0,7–1 s de CPU | ADR-002 |
| Δ RSS do parse (Dancor) | ~+422 MB — **monitorar** | ADR-002 |
| Requisições a geo no carregamento da página | **0** | B-17 |
| `<canvas>` no DOM no carregamento | **0** | B-17 |
| Razão de compressão da geometria | ~5,8× | medido no ZIP |
| LCP em produção | medir com Lighthouse real e **registrar** | pendência da POC |
| CLS | < 0,1 (hoje 0,971) | BILDS-550 |

### 9.4 Verificações de review que não são óbvias

- Todo `@Cron` começa com a trava `ENABLE_CRON_JOBS`.
- Todo `process.send` de worker usa a forma com callback.
- Nenhum `process.env` fora do `env.ts`.
- Toda rota nova respeita a ordem fixo-antes-de-dinâmico.
- Toda string visível existe nos três locales.
- Nenhum `catalogUrl`/`geoBaseUrl` lido sem checar `source`.
- Nenhuma query pública sem `visibility: 'published'`.
- Nenhum `deleteByPrefix` com prefixo montado a partir de entrada de usuário sem
  sanitização.
- `pnpm audit` rodado se alguma dependência entrou.
- `docs/modules/bim-3d-module.md` atualizado no mesmo PR (inclusive as correções de §3.2).

---

## 10. Decisões que precisam de dono humano

Cada uma bloqueia parte do plano. Recomendação dada, decisão não.

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| **D-1** | Transporte do upload | A: `/files/upload` público + `.aq` no allowlist · B: endpoint autenticado dedicado + prop aditiva no `MediaUploader` · C: PUT pré-assinado | **B.** A abre upload anônimo de 1 GB e usa memoryStorage; C não reusa o componente |
| **D-2** | Onde a miniatura é gerada | 1: worker dedicado (imagem glibc + Chromium) · 2: trocar a base da imagem da API para bookworm-slim · 3: usar `SIMBOLOGIA_3D.IMAGEM` (100×100) · 4: não gerar | **1**, no incremento 2. **3** só como placeholder. **4** é o LCP de 39,9 s |
| **D-3** | Limites de recurso do pod | Confirmar memória, CPU e `ephemeral-storage` com quem opera o EKS | Sem isso, um `.aq` de 618 MB é aposta. Não há manifesto no repo |
| **D-4** | Retenção do `.aq` bruto no S3 | Guardar indefinidamente · lifecycle de 30/90 dias · não guardar | Guardar com **lifecycle de 90 dias**: habilita reprocessamento e dedup sem acumular |
| **D-5** | Quem pode gerar catálogo | Qualquer empresa · só `partner: true` · só admin Bilds no começo | **Só `partner: true`** no self-service, com admin Bilds podendo por qualquer empresa (bypass KTD-10 já existe) |
| **D-6** | O `.aq` também vira `libraryFile` para download? | Sim (aparece no portal para download) · não (só gera catálogo) · opcional por checkbox | **Opcional, com default desligado.** São `.aq` de centenas de MB; download não é o caso de uso óbvio |
| **D-7** | `skipMarkers` no parse | Ligado (remove bocais da bbox) · desligado (como a POC) | **Ligado**, e comparar uma miniatura antes/depois. A POC não liga, então a mudança tem efeito visível no enquadramento |
| **D-8** | Nomes de campo da resposta pública | Manter PT (`titulo`, `produtos`) e não tocar no frontend · padronizar EN e ajustar 5 componentes | **PT no incremento 1**, com dívida registrada. Evita repetir o B-15 sob pressão |
| **D-9** | Aposentar o upload de ZIP | Manter os dois · depreciar o ZIP após N catálogos migrados | **Manter os dois.** Nenhum dos 9 catálogos precisa migrar para o novo caminho funcionar |
| **D-10** | Default de `visibility` | `'draft'` + backfill dos existentes · `'published'` | **`'draft'` + backfill**, no mesmo PR |

---

## 11. Mapa de arquivos de referência

### 11.1 bilds.com — ler antes de implementar

| Arquivo | Por quê |
|---|---|
| `CLAUDE.md` | Convenções obrigatórias. Não é opcional |
| `docs/modules/bim-3d-module.md` | O módulo hoje: KTDs, 19 bugs catalogados, i18n, testes. **Corrigir com §3.2** |
| `docs/architecture/patterns.md` (§"Padrão de Cron Jobs", linha 1292) | Forma exata do cron |
| `docs/company/manufacturers-portal.md` | Superfícies do fabricante, cards, download |
| `apps/api/src/b-bim-3d/services/bim-catalog.service.ts` | `assertPermission`, storage condicional, validações, rollback |
| `apps/api/src/b-bim-3d/controllers/bim-catalog.controller.ts` | Ordem das rotas, `serveLocalFile` |
| `apps/api/src/b-bim-3d/schemas/bim-catalog.schema.ts` | O que precisa mudar (§5.6) |
| `apps/api/src/common/services/s3.service.ts` | O que existe e o que falta (§3.5) |
| `apps/api/src/files/controllers/files.controller.ts` | Allowlist, validadores, `@PublicAccess()` |
| `apps/api/src/files/utils/allowed-content-type.util.ts` | Regra de magic bytes por extensão |
| `apps/api/src/webhooks-outbound/services/webhook-delivery-processor.service.ts` | **O padrão de job da casa** |
| `apps/api/src/webhooks-outbound/repositories/webhook-deliveries.repository.ts` (`claimNextBatch`, linha 61) | O claim atômico a copiar |
| `apps/api/src/config/env/env.ts` | Onde declarar toda var nova |
| `apps/api/Dockerfile` · `.github/workflows/development-api.yaml` | O runtime real (Alpine, EKS, `--ignore-scripts`) |
| `apps/web/src/components/UploadFile/MediaUploader.tsx` | O componente a reusar |
| `apps/web/src/queries/medias.ts` | O progresso de upload que já existe |
| `apps/web/src/containers/Company/EditCompany/steps/LibrariesAndFiles.tsx` | Precedente de `MediaUploader` com biblioteca BIM |
| `apps/web/src/components/b-bim-3d/bim-viewer-engine.ts` | `buildScene()` — a referência da miniatura |
| `apps/web/src/components/b-bim-3d/types.ts` · `containers/BimCatalog/BimCatalog.tsx` | O que o consumidor espera hoje |
| `apps/web/src/queries/index.ts` | `tagTypes` — registrar tag nova |
| `apps/admin/src/queries/bim-catalog.ts` · `apps/admin/src/app/b-bim-3d/**` | O admin de hoje |

### 11.2 bilds-bim-3d (POC) — o código a portar

> Outro repositório. Não estará disponível no runtime da bilds.com: **copie o que for
> usar** e cite a origem no comentário do arquivo.

| Arquivo | O que tirar dele |
|---|---|
| `www/tools/aq-reader.ts` | Leitura do `.aq` inteira. Porta quase literal |
| `www/tools/oq3d-parser.ts` | Parser OQ3D com os dois bugs corrigidos. Porta literal |
| `www/apps/api/src/importacoes/parse-worker.ts` | `dedupBuffers`, extração de catálogo/produto, `slugify`, montagem de `specs`/`curva` |
| `www/apps/api/src/importacoes/importacoes.service.ts` | Máquina de estados, upsert com substituição, cleanup, fire-and-forget da miniatura |
| `www/apps/api/src/importacoes/thumb-worker.ts` | Laço de miniatura, isolamento de erro por produto, `closeThumbRenderer` no `finally` |
| `www/tools/thumb-rasterizer.ts` | Sessão de browser única, fila, string JSON no `evaluate`, args de SwiftShader, tradução do erro de lib ausente |
| `templates/thumbs/harness.html` | `buildScene()` + câmera. **Mantenha em sincronia com o viewer** |
| `www/apps/api/src/common/asset-cache.ts` | ETag/304 — e a justificativa de por que não `immutable` |
| `www/apps/api/src/geometry-store/*` | Interface e implementação de disco (com `stat`) |
| `www/apps/api/src/{bim-imports,bim-products,bim-catalogs}/*.schema.ts` | Base dos schemas |
| `www/apps/api/src/importacoes/importacoes.controller.ts` | `diskStorage`, limite de 750 MB, ordem de rota `ultima` |
| `www/apps/web/src/app/empresa/importar/page.tsx` | **Lógica** de progresso e recuperação. Refaça a apresentação |
| `www/tools/regen-thumbs.ts` | Precedente da rota de reprocessamento |
| `docs/bilds-bim-3d-zip-spec.md` | Contrato do ZIP: campos, geo JSON, miniatura (§4.1 lá) |
| `docs/solutions/architecture-patterns/poc-catalogo-bim-dinamico-aprendizados.md` | O destilado, com os números |
| `docs/solutions/architecture-patterns/thumb-qualidade-identica-ao-viewer.md` | A decisão da miniatura em detalhe |
| `docs/sessoes/S6.1-cache-de-assets.md` (§4 e §6) | Cache e visibilidade — as duas coisas que S6.1 mandou levar |
| `CLAUDE.md` (seções "Conhecimento crítico") | `oq3d.py`, `read_aq.py`, templates: as armadilhas na origem |

---

## 12. Resumo em uma página

- **O que muda:** o fabricante sobe o `.aq` pela plataforma; a API faz o que hoje uma
  máquina local faz; o catálogo passa a viver no banco em vez de num `catalog.json`.
- **O que reusar sem discussão:** `MediaUploader` (progresso de upload já existe),
  `assertPermission`, `S3Service`, o padrão de job com claim atômico do
  `webhooks-outbound`, as rotas públicas e todos os componentes de apresentação do
  catálogo.
- **O que portar da POC:** `aq-reader`, `oq3d-parser`, `dedupBuffers`, a máquina de
  estados, o renderizador de miniatura com Playwright, o `GeometryStore`, o `asset-cache`.
- **O que melhorar em relação à POC:** chaves **content-addressed** (habilita `immutable`,
  deduplica geometria e miniatura, torna reimportação barata), geometria **gzipada**,
  execução resiliente a restart de pod, **visibilidade** de catálogo, e o `.aq` bruto
  guardado para reprocessar.
- **O maior risco técnico:** Chromium para miniatura fiel numa imagem **Alpine** com
  `pnpm install --ignore-scripts` e `USER` não-root. Não dá para contornar sem uma decisão
  de infraestrutura (**D-2**).
- **O maior risco de produto:** publicar catálogo sem controle de visibilidade
  (**D-10**/§5.7).
- **O erro mais provável de repetir:** dedup ausente ou dedupando só por posição (A-11,
  A-12), rotação lida como row-major (A-4), e `process.send` sem flush (A-16). Os três são
  silenciosos: nada quebra, só sai errado.
