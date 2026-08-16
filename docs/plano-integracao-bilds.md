# Plano de integração: bilds-bim-3d → bilds.com

> ## 🔴 LEIA O `CLAUDE.md` DO REPOSITÓRIO BILDS.COM ANTES DE QUALQUER COISA
>
> O `CLAUDE.md` presente na raiz do repositório bilds.com é **soberano**. Ele se sobrepõe a qualquer instrução deste documento. Se houver conflito entre o que está escrito aqui e o que está no `CLAUDE.md`, siga o `CLAUDE.md` sem exceção. Este plano foi escrito sem acesso à versão atual do codebase — o `CLAUDE.md` tem a versão real das convenções, estruturas e regras do projeto.
>
> Leia o `CLAUDE.md` completo antes de abrir qualquer outro arquivo ou tomar qualquer decisão de implementação.

**Gerado em:** 2026-08-16  
**Destino:** agente trabalhando no codebase bilds.com (dashboard + API + web)  
**Repositório de origem:** `carlosnetoaltoqi/bilds-bim-3d`

---

## Contexto para o agente

Existe um pipeline local chamado `bilds-bim-3d` que recebe arquivos `.aq` (biblioteca AltoQi) e `.IFC` (geometria 3D) e gera dois artefatos:

1. **`output/preview/{slug}/index.html`** — preview HTML local para revisar o catálogo
2. **`output/bilds-upload.zip`** — pacote para upload na bilds.com

Sua tarefa é implementar o lado da bilds.com que recebe esse ZIP e serve o catálogo como uma página pública React/Next.js com SEO adequado.

**Restrição crítica:** a página servida em `bilds.com/[empresa]/[slug]` deve ser uma rota Next.js normal renderizada server-side — não um iframe. O conteúdo precisa ser indexável por SEO e usar `generateMetadata()`.

Antes de qualquer implementação, leia o `CLAUDE.md` do repositório bilds.com para entender a estrutura existente, padrões de código e regras de operação.

---

## ⛔ REGRA INVIOLÁVEL — Nenhum arquivo existente pode ser modificado

**Esta regra se sobrepõe a qualquer outra instrução deste documento.**

Toda a implementação descrita neste plano deve ser feita **exclusivamente através da criação de arquivos novos**. Nenhum arquivo já existente no repositório bilds.com deve ser alterado, editado, refatorado ou ter linhas adicionadas — independentemente do motivo, da conveniência técnica ou de qualquer otimização aparente.

**O que é permitido:**
- Criar novos arquivos de rota (`page.tsx`, `layout.tsx`, `route.ts`)
- Criar novos componentes em pastas novas
- Criar novos schemas/DTOs/módulos no NestJS
- Criar novas páginas no dashboard em rotas novas
- Adicionar novo campo ao schema MongoDB (via migration ou subdocumento isolado)
- Instalar novas dependências (apenas adição ao `package.json`, não remoção ou alteração de versões existentes)

**O que é proibido — mesmo que pareça necessário:**
- Editar qualquer `page.tsx`, `layout.tsx`, `component.tsx` já existente
- Editar qualquer controller, service ou module NestJS já existente
- Editar qualquer schema Mongoose/MongoDB já existente (usar extensão via novo campo isolado)
- Editar menus de navegação existentes — a entrada "BIM 3D" deve ser adicionada de forma que não altere o arquivo do menu atual (verifique se o menu já tem um mecanismo de extensão/registro; se não tiver, crie o item somente se for possível sem editar o arquivo do menu)
- Editar arquivos de configuração (`vercel.json`, `turbo.json`, `tsconfig`, etc.)
- Editar qualquer arquivo de estilo global
- Refatorar, renomear ou reorganizar qualquer coisa existente

**Em caso de dúvida:** se a tarefa parecer exigir a modificação de um arquivo existente, pare e registre o bloqueio em vez de editar. O operador decidirá como resolver.

---

## 1. O que o ZIP contém

```
bilds-upload.zip
├── manifest.json       ← metadados do catálogo
├── catalog.json        ← dados completos (produtos, specs, curvas Q-H)
└── geo/
    ├── cam-w10.json    ← geometria 3D de cada produto
    ├── cam-w14.json
    └── ...
```

### manifest.json

```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "fabricante": "Dancor",
  "descricao": "Linha CAM-W e TJM para sistemas prediais.",
  "layout": "series-rows",
  "filtros": ["CAM-W", "TJM"],
  "n_produtos": 14
}
```

### catalog.json — schema completo

```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "fabricante": "Dancor",
  "descricao": "Linha CAM-W e TJM para sistemas prediais.",
  "layout": "series-rows",
  "filtros": ["CAM-W", "TJM"],
  "produtos": [
    {
      "id": "cam-w10",
      "nome": "CAM-W10 1CV T 220/380V INC FLG IR3",
      "serie": "CAM-W10",
      "geo": "cam-w10.json",
      "potencia": 1.0,
      "conexoes": "1½\" × 1½\"",
      "specs": {
        "Tensão": "Trifásico 220/380V",
        "Grau de Proteção": "IP55-TFVE",
        "Isolamento": "Classe F",
        "Rotação": "3.500 rpm · 60Hz"
      },
      "curva": [
        [0.5, 22.1, 1.0, 42.3],
        [1.0, 20.8, 1.0, 55.1],
        [1.5, 18.2, 1.0, 60.4],
        [2.0, 14.1, 1.0, 58.2]
      ]
    }
  ]
}
```

**Campos de produto:**
- `id` — string, slug URL-safe, corresponde ao nome do arquivo geo (sem `.json`)
- `nome` — string, nome comercial completo
- `serie` — string, família/série do produto
- `geo` — string, nome do arquivo JSON de geometria (`cam-w10.json`)
- `potencia` — number | null, potência em CV
- `conexoes` — string, ex: `"1½\" × 1½\""`
- `specs` — object chave/valor livre de strings
- `curva` — array de `[vazao_m3h, altura_mca, potencia_cv, rendimento_pct]` | null

### geo/{slug}.json — buffer Three.js

```json
{
  "pos": [x0, y0, z0, x1, y1, z1, ...],
  "col": [r0, g0, b0, r1, g1, b1, ...],
  "idx": [a0, b0, c0, ...]
}
```

- `pos`: vértices flat (3 floats/vértice), metros, Y-up
- `col`: cor RGB por vértice, 0–1. Se `col` for vazio, usar cor padrão `[0.72, 0.75, 0.80]`
- `idx`: índices de triângulos. Se ausente, cada 3 vértices formam um triângulo

---

## 2. Dois layouts — comportamento esperado

O campo `layout` em `manifest.json` define qual componente React renderizar:

| Valor | Comportamento |
|---|---|
| `series-rows` | Linhas estilo Netflix — uma linha horizontal por série (`serie`), scroll horizontal por linha, modal ao clicar. Para catálogos com poucas famílias e muitos itens por família. |
| `catalog-grid` | Grid denso com chips de filtro no topo — filtra por `serie`. Para catálogos heterogêneos com muitos itens de tipos diferentes. |

Ambos os layouts exibem o viewer 3D (lazy), as specs do produto e a curva Q-H (SVG inline).

---

## 3. MongoDB — campo novo em Company

Adicione o subdocumento `bBim3d` ao schema de Company existente. **Não altere campos existentes** (`libraryFiles`, `name`, `customLink`, etc.).

```typescript
// Novo subdocumento
class BBim3dEntry {
  slug: string;          // 'bombas-incendio' — único por empresa
  titulo: string;
  fabricante: string;
  descricao: string;
  layout: 'series-rows' | 'catalog-grid';
  filtros: string[];
  nProdutos: number;
  catalogUrl: string;    // URL CloudFront do catalog.json
  geoBaseUrl: string;    // URL CloudFront prefixo dos geo/ (sem nome de arquivo)
  publishedAt: Date;
  active: boolean;
}

// Em Company, novo campo:
bBim3d: BBim3dEntry[];   // padrão: []
```

O `catalogUrl` aponta para onde o catalog.json completo está no CloudFront:
```
https://{CLOUDFRONT_BASE}/b-bim-3d/{slug-empresa}/{slug-catalogo}/catalog.json
```

O `geoBaseUrl` é o prefixo base dos arquivos de geometria:
```
https://{CLOUDFRONT_BASE}/b-bim-3d/{slug-empresa}/{slug-catalogo}/geo/
```

Para carregar a geometria de um produto: `geoBaseUrl + produto.geo`
Ex: `https://storage.bilds.com/b-bim-3d/dancor/bombas-incendio/geo/cam-w10.json`

---

## 4. API NestJS — endpoint de upload

```
POST /companies/:id/b-bim-3d
Content-Type: multipart/form-data
Authorization: Bearer {token-admin}

Campos:
  zip (File) — o arquivo bilds-upload.zip
```

**Lógica do endpoint:**

1. Validar que o usuário autenticado é admin da empresa `id` (mesmo guard dos endpoints de edição existentes)
2. Extrair o ZIP em memória (sem escrever em disco): ler `manifest.json` e `catalog.json`
3. Para cada arquivo em `geo/`: fazer upload para S3 com `S3Service` no path:
   ```
   b-bim-3d/{customLink-da-empresa}/{manifest.slug}/geo/{nome-arquivo}
   ```
4. Fazer upload do `catalog.json` para S3:
   ```
   b-bim-3d/{customLink-da-empresa}/{manifest.slug}/catalog.json
   ```
5. Construir URLs do CloudFront usando `process.env.AWS_CLOUD_FRONT_BASE_URL`
6. Upsert em `company.bBim3d` (slug é chave — se já existe, atualiza; se não, insere)
7. Retornar o `BBim3dEntry` salvo

**Resposta:**
```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "catalogUrl": "https://storage.bilds.com/b-bim-3d/dancor/bombas-incendio/catalog.json",
  "geoBaseUrl": "https://storage.bilds.com/b-bim-3d/dancor/bombas-incendio/geo/",
  "publishedAt": "2026-08-16T00:00:00.000Z",
  "active": true
}
```

**Endpoint adicional para trocar layout sem re-upload:**
```
PATCH /companies/:id/b-bim-3d/:slug
Body: { layout: 'series-rows' | 'catalog-grid' }
```

Esse endpoint só atualiza o campo `layout` no banco — sem alterar os arquivos no S3.

---

## 4b. Autenticação e permissões

### Endpoints da API (NestJS) — protegidos

Ambos os endpoints (`POST` e `PATCH`) exigem autenticação. Use exatamente os mesmos guards e decorators que os endpoints de edição de empresa já existentes no codebase — não implemente uma nova lógica de autenticação.

Antes de criar os endpoints, leia o controller de empresa existente (`companies.controller.ts` ou equivalente) e identifique:
- Qual decorator/guard é usado para exigir autenticação (ex: `@UseGuards(JwtAuthGuard)`)
- Qual decorator/guard verifica se o usuário é dono/admin da empresa (ex: `@UseGuards(CompanyOwnerGuard)`)
- Como o usuário autenticado é extraído da request (ex: `@CurrentUser()`, `@Req()`)

Aplique esses mesmos guards nos novos endpoints sem adaptação ou cópia de lógica:

```typescript
// Exemplo — use os guards reais do codebase, não invente novos
@Post(':id/b-bim-3d')
@UseGuards(JwtAuthGuard, CompanyOwnerGuard)   // ← copie os guards dos endpoints existentes
@UseInterceptors(FileInterceptor('zip'))
async uploadBBim3d(
  @Param('id') id: string,
  @UploadedFile() file: Express.Multer.File,
) { ... }

@Patch(':id/b-bim-3d/:slug')
@UseGuards(JwtAuthGuard, CompanyOwnerGuard)
async updateLayout(...) { ... }
```

**Nível de acesso:** apenas o usuário que é dono ou admin da empresa com o `id` informado. Nenhum outro usuário — nem outros admins de empresas diferentes — pode publicar ou alterar catálogos de uma empresa que não é sua.

### Dashboard (dashboard.bilds.com) — protegido

Todas as páginas do dashboard já ficam atrás de autenticação pelo layout/middleware existente. As novas rotas `/b-bim-3d`, `/b-bim-3d/:companyId` herdam essa proteção automaticamente por estarem dentro da estrutura de rotas autenticadas do dashboard. Não é necessário nenhum guard adicional nas páginas — apenas siga a estrutura de pastas já existente.

### Rota pública `bilds.com/[customLink]/[catalogSlug]` — completamente pública

Esta rota é **totalmente pública, sem autenticação, sem sessão, sem middleware de proteção** de nenhum tipo. Qualquer pessoa, inclusive robôs de busca (Googlebot, etc.), deve conseguir acessar a URL sem nenhum cookie ou token.

Verifique se existe algum middleware global de autenticação no `apps/web` que pudesse interceptar essa rota — se existir, a nova rota `[catalogSlug]` deve ser explicitamente excluída do matcher desse middleware. Leia o `middleware.ts` (se existir) antes de finalizar a implementação da rota.

A rota segue o modelo padrão de **página pública do bilds.com** — o mesmo que a página de empresa `[customLink]/page.tsx` e outras rotas públicas do site. Não adicione nenhuma verificação de sessão dentro do server component da rota do catálogo.

```typescript
// apps/web/src/app/[customLink]/[catalogSlug]/page.tsx
// Server component — sem getServerSession(), sem redirect para login, sem auth check
export default async function BimCatalogPage({ params }) {
  // Busca dados do banco/CloudFront — público
  // Retorna a página — público
}
```

**`generateMetadata()` também é público** — roda no servidor sem nenhuma verificação de autenticação. Os metadados de título, descrição e OpenGraph são gerados para qualquer visitante, incluindo crawlers de SEO.

---

## 5. Dashboard — menu e interface de upload

### 5.1 Novo item no menu lateral

Adicione "BIM 3D" como item de menu em `dashboard.bilds.com`. O ícone sugerido é `Box` ou `Package` do Lucide. A rota pode ser `/b-bim-3d`.

### 5.2 Página `/b-bim-3d` — grid de empresas

Lista as empresas que têm `bBim3d.length > 0`. Use o padrão de grid existente no dashboard. Cada card mostra:
- Nome da empresa
- Número de catálogos publicados
- Botão "Gerenciar" → `/b-bim-3d/{company-id}`

### 5.3 Página `/b-bim-3d/{company-id}` — gerenciamento por empresa

Lista os catálogos da empresa com:
- Nome, fabricante, layout, data de publicação, botão "Ver" (abre `bilds.com/{customLink}/{slug}`)
- Botão "Trocar layout" (PATCH endpoint — abre dropdown com miniatura dos dois layouts)
- Botão "Substituir" (re-upload do ZIP)
- Botão "Novo catálogo" → abre formulário

### 5.4 Formulário de upload

Campos:
- **Arquivo ZIP** (react-dropzone, aceita `.zip`)
- Preview dos metadados extraídos do ZIP antes de confirmar (lê o `manifest.json` do ZIP no browser antes de enviar)
- **Seleção de layout** com miniaturas dos dois layouts (imagens estáticas ou SVG esquemático)
  - `series-rows`: esquema visual de linhas horizontais com cards
  - `catalog-grid`: esquema visual de grade densa com filtros no topo

Use react-hook-form + zod conforme o padrão existente no dashboard. O layout selecionado no formulário sobrescreve o do `manifest.json`.

**Miniaturas dos layouts (para o formulário de seleção):**
Use SVG inline simples — não dependência externa:

```
series-rows:           catalog-grid:
┌──────────────────┐   ┌──────────────────┐
│ Série A ─────────│   │ [filtro][filtro]  │
│ [□][□][□]→       │   │ [□][□][□][□][□]  │
│ Série B ─────────│   │ [□][□][□][□][□]  │
│ [□][□]→          │   │ [□][□][□][□][□]  │
└──────────────────┘   └──────────────────┘
```

---

## 6. bilds.com — rota pública

### 6.1 Rota

```
apps/web/src/app/[customLink]/[catalogSlug]/page.tsx
```

**Conflito de rotas:** Next.js App Router prioriza segmentos estáticos sobre segmentos dinâmicos. As rotas fixas existentes em `[customLink]/` (`editar`, `avaliacoes`, `seguir`, etc.) continuam funcionando sem conflito porque `[catalogSlug]` só captura quando não há rota estática correspondente.

### 6.2 Server component com generateMetadata

```typescript
import { Metadata } from 'next'
import { notFound } from 'next/navigation'

interface Props {
  params: { customLink: string; catalogSlug: string }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const catalog = await getCatalogData(params.customLink, params.catalogSlug)
  if (!catalog) return {}
  return {
    title: `${catalog.titulo} — ${catalog.fabricante} · bilds`,
    description: catalog.descricao,
    openGraph: {
      title: `${catalog.titulo} — ${catalog.fabricante}`,
      description: catalog.descricao,
      type: 'website',
    },
  }
}

export default async function BimCatalogPage({ params }: Props) {
  const { company, catalog, catalogData } = await getCatalogData(params.customLink, params.catalogSlug)
  if (!catalog) notFound()

  return <BimCatalogView catalog={catalogData} layout={catalog.layout} geoBaseUrl={catalog.geoBaseUrl} />
}
```

`getCatalogData`:
1. Busca a empresa pelo `customLink` (padrão existente do codebase)
2. Encontra o `BimCatalog` pelo `catalogSlug` dentro de `company.bBim3d`
3. Faz `fetch(catalog.catalogUrl)` para obter o `catalog.json` completo com os produtos
4. Retorna `{ company, catalog, catalogData }`

### 6.3 Componentes React necessários

Crie dentro de `apps/web/src/components/b-bim-3d/` (ou onde o codebase organiza componentes):

#### `BimCatalogView` (server component wrapper)

Renderiza o layout correto conforme `catalog.layout`:

```typescript
'use client'  // ou server — ver nota abaixo sobre Three.js

export function BimCatalogView({ catalog, layout, geoBaseUrl }) {
  if (layout === 'series-rows') return <SeriesRowsLayout catalog={catalog} geoBaseUrl={geoBaseUrl} />
  if (layout === 'catalog-grid') return <CatalogGridLayout catalog={catalog} geoBaseUrl={geoBaseUrl} />
  return null
}
```

#### `SeriesRowsLayout` — linhas Netflix por série

- Agrupa `catalog.produtos` por `serie`
- Para cada série: título da série + linha horizontal com scroll + cards de produto
- Cada card: nome do produto, potência, conexões, badge de série
- Click no card abre `ProductModal`

#### `CatalogGridLayout` — grid denso com filtros

- Chips de filtro no topo (usa `catalog.filtros`)
- Grid de cards filtráveis por série
- Click no card abre `ProductModal`

#### `ProductModal`

Modal com:
- Viewer 3D (`BimViewer`, carregado via `dynamic(() => import('./BimViewer'), { ssr: false })`)
- Specs do produto (chave/valor de `produto.specs`)
- Curva Q-H em SVG (`CurveChart`, pode ser SSR pois é SVG puro)
- Nome, potência, conexões

#### `BimViewer` (importado com `ssr: false`)

```typescript
'use client'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useEffect, useRef } from 'react'

export function BimViewer({ geoUrl }: { geoUrl: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    // fetch(geoUrl) → buildScene → renderer.render() (1 frame estático)
    // click no canvas → ativa OrbitControls + requestAnimationFrame
  }, [geoUrl])

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
}
```

`three` deve ser instalado como dependência do app web:
```bash
pnpm add three @types/three --filter @bilds/web  # (ou o nome do workspace)
```

#### `CurveChart` — curva Q-H em SVG (SSR-safe)

Recebe `curva: [vazao, altura, potencia, rendimento][]` e renderiza SVG com:
- Eixo X: vazão (m³/h)
- Linha azul `#1E40AF`: curva Q-H (altura manométrica)
- Linha cinza tracejada: rendimento
- Grid horizontal
- Labels nos eixos

Pode ser server component puro (sem `useEffect`) — SVG calculado em render.

---

## 7. Design tokens a usar

A página BIM segue o **Bilds Design System v2.1** — se o codebase bilds.com já importa o design system, use os tokens existentes. Se precisar declarar localmente:

| Token | Valor | Uso |
|---|---|---|
| Orange | `#FF4F1F` | Somente CTA principal da página |
| Blue | `#1E40AF` | Botão dentro de card, links |
| Navy | `#002D72` | Badges default, eyebrow, ícones |
| Navy light | `#DFE8FA` | Badge secondary bg |
| Muted | `#FAFBFB` | Fundo de seção alternativo |
| Text primary | `#111827` | Títulos e corpo |
| Text secondary | `#6B7280` | Subtítulos, metadados |
| Border | `#E5E7EB` | Borda de card |
| Border radius | `4px` | Universal — exceto badges: `9999px` |
| Sombra padrão | nenhuma | Sombra só no hover de card interativo |

Tipografia:
- **Fira Sans 800** — somente títulos de seção ≥ 30px (hero, heading da biblioteca)
- **Inter** — todo o resto: subtítulos, nomes de produto, specs, botões, badges

---

## 8. Ordem de implementação sugerida

1. **MongoDB**: adicionar `bBim3d: BBim3dEntry[]` ao schema de Company
2. **API**: endpoint `POST /companies/:id/b-bim-3d` com extração do ZIP e upload S3
3. **API**: endpoint `PATCH /companies/:id/b-bim-3d/:slug` (troca de layout)
4. **Dashboard**: menu "BIM 3D" + páginas de listagem e upload
5. **bilds.com web**: rota `[customLink]/[catalogSlug]` com stub (mostra título + fabricante)
6. **Componentes**: `CurveChart` (SVG, sem dependência externa)
7. **Componentes**: `SeriesRowsLayout` e `CatalogGridLayout` com cards estáticos
8. **Componentes**: `BimViewer` com Three.js (instalar `three` no workspace)
9. **Componentes**: `ProductModal` conectando viewer + curva + specs
10. **SEO**: `generateMetadata` completo
11. Teste end-to-end com ZIP real

---

## 9. Templates HTML de referência — implementação fiel obrigatória

Os dois layouts React devem replicar fielmente os templates HTML abaixo.
O CSS, a lógica JS (filtros, modal, chart, Three.js) e a estrutura HTML são a fonte da verdade.
Na conversão para React:
- Topbar/header do template é removido — o bilds.com já tem o seu
- `{{ catalog | tojson | safe }}` vira props React
- O bloco `<script type="module">` (Three.js) vira o componente `BimViewer` com `dynamic(() => import(), {ssr:false})`
- A função `buildChart()` vira o componente `CurveChart` (SVG puro, pode ser SSR)
- CSS pode ser CSS Module, styled-jsx ou Tailwind — manter as dimensões e comportamentos

### Layout `series-rows` — template completo

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ catalog.titulo }} | {{ catalog.fabricante }} | bilds</title>
<meta name="description" content="{{ catalog.descricao }}">
<script type="importmap">{"imports":{"three":"/vendor/three.module.js"}}</script>
<style>
/* ─── Reset + tokens bilds ──────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --orange:#FF4F1F;--blue:#1E40AF;--bg:#F8F9FA;--surface:#fff;
  --text:#111827;--muted:#6B7280;--border:#E5E7EB;
  --radius:4px;--header:64px;
  font-family:'Inter',system-ui,sans-serif;
}
body{background:var(--bg);color:var(--text);min-height:100vh}

/* ─── Topbar ────────────────────────────────────────────────── */
.topbar{
  position:sticky;top:0;z-index:100;height:var(--header);
  background:#fff;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:16px;padding:0 24px;
}
.topbar-logo{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px;text-decoration:none;color:var(--text)}
.topbar-logo svg{color:var(--orange)}
.topbar-sep{color:var(--border);font-size:20px}
.topbar-title{font-size:14px;color:var(--muted)}
.topbar-cta{
  margin-left:auto;
  background:var(--orange);color:#fff;border:none;border-radius:var(--radius);
  padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer;
  text-decoration:none;
}

/* ─── Hero ──────────────────────────────────────────────────── */
.hero{padding:40px 24px 24px;max-width:1200px;margin:0 auto}
.hero h1{font-family:'Fira Sans',sans-serif;font-size:clamp(22px,4vw,32px);font-weight:700;margin-bottom:8px}
.hero-sub{color:var(--muted);font-size:14px}

/* ─── Filter bar ────────────────────────────────────────────── */
.filter-bar{
  display:flex;gap:8px;padding:0 24px 24px;max-width:1200px;margin:0 auto;
  flex-wrap:wrap;
}
.chip{
  padding:6px 14px;border-radius:9999px;border:1px solid var(--border);
  background:#fff;font-size:13px;cursor:pointer;transition:all .15s;
}
.chip.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.chip:hover:not(.active){border-color:var(--blue);color:var(--blue)}

/* ─── Rows ──────────────────────────────────────────────────── */
.section{padding:0 24px 40px;max-width:1200px;margin:0 auto}
.section-head{
  display:flex;align-items:baseline;gap:12px;margin-bottom:12px;
}
.section-head h2{font-family:'Fira Sans',sans-serif;font-size:18px;font-weight:600}
.section-count{font-size:12px;color:var(--muted)}
.row-outer{position:relative}
.row-outer::before,.row-outer::after{
  content:'';position:absolute;top:0;bottom:16px;width:28px;
  z-index:10;pointer-events:none;
}
.row-outer::before{left:0;background:linear-gradient(to right,var(--bg),transparent)}
.row-outer::after{right:0;background:linear-gradient(to left,var(--bg),transparent)}
.row-track{
  display:flex;gap:12px;overflow-x:auto;padding:4px 0 16px;
  scroll-snap-type:x mandatory;scrollbar-width:none;
}
.row-track::-webkit-scrollbar{display:none}

/* ─── Card ──────────────────────────────────────────────────── */
.card{
  flex-shrink:0;width:224px;scroll-snap-align:start;
  background:var(--surface);border-radius:var(--radius);
  border:1px solid var(--border);cursor:pointer;
  transition:box-shadow .15s,transform .15s;
}
.card:hover{box-shadow:0 4px 16px rgba(0,0,0,.1);transform:translateY(-2px)}
.card-canvas-wrap{position:relative;height:162px;background:#F3F4F6;border-radius:var(--radius) var(--radius) 0 0;overflow:hidden}
.card-canvas-wrap canvas{width:100%;height:100%;display:block}
.card-loader{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-size:11px;color:var(--muted);
}
.badge-3d{
  position:absolute;top:8px;right:8px;width:28px;height:28px;
  background:rgba(255,255,255,.93);border-radius:var(--radius);
  display:flex;align-items:center;justify-content:center;cursor:pointer;
  transition:opacity .25s;
}
.badge-3d svg{width:16px;height:16px;stroke:var(--orange);stroke-width:2;fill:none}
.badge-3d.off{opacity:0;pointer-events:none}
.card-body{padding:12px}
.card-name{font-size:13px;font-weight:600;margin-bottom:4px;line-height:1.3}
.card-meta{font-size:11px;color:var(--muted);margin-bottom:10px}
.card-btn{
  width:100%;padding:7px;border-radius:var(--radius);
  border:1px solid var(--blue);color:var(--blue);background:#fff;
  font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;
}
.card-btn:hover{background:var(--blue);color:#fff}

/* ─── Modal ─────────────────────────────────────────────────── */
.modal-backdrop{
  position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.5);
  backdrop-filter:blur(4px);display:none;
  align-items:center;justify-content:center;padding:16px;
}
.modal-backdrop.open{display:flex}
.modal{
  background:#fff;border-radius:var(--radius);
  width:100%;max-width:820px;max-height:92vh;
  overflow-y:auto;display:flex;flex-direction:column;
  animation:slideUp .2s ease;
}
@keyframes slideUp{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}
.modal-head{
  position:sticky;top:0;background:#fff;z-index:10;
  display:flex;align-items:center;gap:12px;padding:16px 20px;
  border-bottom:1px solid var(--border);
}
.modal-head h3{font-size:16px;font-weight:600;flex:1}
.modal-close{
  background:none;border:none;cursor:pointer;padding:4px;
  color:var(--muted);border-radius:var(--radius);
}
.modal-close:hover{background:var(--border)}
.modal-3d{height:300px;background:#F3F4F6;position:relative}
.modal-3d canvas{width:100%;height:100%;display:block}
.modal-body{padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:20px}
.specs-table{font-size:13px;border-collapse:collapse;width:100%}
.specs-table th{text-align:left;font-weight:500;color:var(--muted);padding:5px 0;width:45%}
.specs-table td{padding:5px 0;border-bottom:1px solid var(--border)}
.modal-actions{
  position:sticky;bottom:0;background:#fff;z-index:10;
  padding:12px 20px;border-top:1px solid var(--border);
  display:flex;gap:8px;justify-content:flex-end;
}
.btn-primary{
  background:var(--orange);color:#fff;border:none;border-radius:var(--radius);
  padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;
}
.btn-outline{
  background:#fff;color:var(--muted);border:1px solid var(--border);
  border-radius:var(--radius);padding:9px 20px;font-size:13px;cursor:pointer;
}

/* ─── Responsivo ────────────────────────────────────────────── */
@media(max-width:600px){
  .topbar{padding:0 16px}
  .hero,.filter-bar,.section{padding-left:16px;padding-right:16px}
  .card{width:196px}
  .card-canvas-wrap{height:142px}
  .modal-body{grid-template-columns:1fr}
  .modal-3d{height:220px}
}
@media(max-width:860px){.topbar-nav{display:none}}
</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
</head>
<body>

<!-- Topbar — REMOVER no React, usar header do bilds.com -->
<header class="topbar">
  <a class="topbar-logo" href="https://bilds.com">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    bilds
  </a>
  <span class="topbar-sep">/</span>
  <span class="topbar-title">{{ catalog.fabricante }}</span>
</header>

<!-- Hero — manter no React -->
<section class="hero">
  <h1>{{ catalog.titulo }}</h1>
  <p class="hero-sub">{{ catalog.descricao }}</p>
</section>

<!-- Filter chips — manter, mas state com useState -->
<div class="filter-bar" id="filter-bar">
  <button class="chip active" data-filter="all" onclick="filterBy('all',this)">Todos</button>
  {% for f in catalog.filtros %}
  <button class="chip" data-filter="{{ f }}" onclick="filterBy('{{ f }}',this)">Série {{ f }}</button>
  {% endfor %}
</div>

<!-- Rows por série — renderizado por renderRows() -->
<div id="rows-root"></div>

<!-- Modal -->
<div class="modal-backdrop" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-head">
      <h3 id="modal-title">—</h3>
      <button class="modal-close" onclick="closeModal()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="modal-3d"><canvas id="modal-canvas"></canvas></div>
    <div class="modal-body">
      <div>
        <h4 style="font-size:13px;font-weight:600;margin-bottom:10px;color:var(--muted)">Especificações</h4>
        <table class="specs-table" id="modal-specs"></table>
      </div>
      <div id="modal-chart-wrap">
        <h4 style="font-size:13px;font-weight:600;margin-bottom:10px;color:var(--muted)">Curva Q-H</h4>
        <div id="modal-chart"></div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn-outline" onclick="closeModal()">Fechar</button>
      <a class="btn-primary" href="https://bilds.com" target="_blank">Ver na bilds</a>
    </div>
  </div>
</div>

<!-- Script 1: sync — dados + renderização dos cards -->
<script>
const CATALOG = {{ catalog | tojson | safe }};
const ITEMS   = CATALOG.produtos;

let activeFilter = 'all';
const geoCache   = new Map();

function matchFilter(item, f) {
  return f === 'all' || item.serie === f;
}

function buildCard(item) {
  return `<div class="card" data-id="${item.id}" onclick="openModal('${item.id}')">
    <div class="card-canvas-wrap">
      <canvas id="canvas-${item.id}" style="cursor:pointer"></canvas>
      <div class="card-loader" id="loader-${item.id}">Carregando…</div>
      <div class="badge-3d" id="badge-${item.id}">
        <svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
      </div>
    </div>
    <div class="card-body">
      <div class="card-name">${item.nome}</div>
      <div class="card-meta">${item.conexoes || (item.potencia ? item.potencia + ' CV' : '')}</div>
      <button class="card-btn">Ver detalhes</button>
    </div>
  </div>`;
}

function buildSection(serie, items) {
  const cards = items.map(buildCard).join('');
  return `<section class="section">
    <div class="section-head">
      <h2>Série ${serie}</h2>
      <span class="section-count">${items.length} modelo${items.length !== 1 ? 's' : ''}</span>
    </div>
    <div class="row-outer">
      <div class="row-track">${cards}</div>
    </div>
  </section>`;
}

function renderRows(filter) {
  activeFilter = filter;
  const filtered = ITEMS.filter(i => matchFilter(i, filter));
  const bySerie = {};
  filtered.forEach(i => {
    const s = i.serie || 'Outros';
    if (!bySerie[s]) bySerie[s] = [];
    bySerie[s].push(i);
  });
  document.getElementById('rows-root').innerHTML =
    Object.entries(bySerie).map(([s, items]) => buildSection(s, items)).join('');
  document.dispatchEvent(new CustomEvent('cards-rendered', {detail:{filter}}));
}

function filterBy(f, el) {
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  renderRows(f);
}

function buildChart(pts, W, H) {
  if (!pts || !pts.length) return '<p style="font-size:12px;color:var(--muted)">Curva não disponível.</p>';
  const pl=40,pr=12,pt=14,pb=36,cW=W-pl-pr,cH=H-pt-pb;
  const qMax=Math.max(...pts.map(p=>p[0]))*1.1;
  const hMax=Math.max(...pts.map(p=>p[1]))*1.18;
  const tx=q=>pl+(q/qMax)*cW, ty=h=>H-pb-(h/hMax)*cH;
  let g='';
  [.25,.5,.75,1].forEach(f=>{
    const yy=ty(hMax*f).toFixed(1);
    g+=`<line x1="${pl}" y1="${yy}" x2="${W-pr}" y2="${yy}" stroke="#E5E7EB" stroke-width="1"/>`;
    g+=`<text x="${pl-5}" y="${+yy+3}" text-anchor="end" fill="#6B7280" font-size="9">${Math.round(hMax*f)}</text>`;
  });
  const path='M'+pts.map(p=>`${tx(p[0]).toFixed(1)},${ty(p[1]).toFixed(1)}`).join('L');
  const area=path+`L${tx(pts.at(-1)[0]).toFixed(1)},${H-pb}L${tx(pts[0][0]).toFixed(1)},${H-pb}Z`;
  const tyEff=e=>H-pb-(Math.min(e,65)/65)*cH;
  const eff=pts[0][3]!=null?'M'+pts.map(p=>`${tx(p[0]).toFixed(1)},${tyEff(p[3]).toFixed(1)}`).join('L'):'';
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" xmlns="http://www.w3.org/2000/svg">
    <rect x="${pl}" y="${pt}" width="${cW}" height="${cH}" fill="#FAFBFB" rx="2"/>
    ${g}
    <path d="${area}" fill="rgba(30,64,175,0.1)"/>
    <path d="${path}" fill="none" stroke="#1E40AF" stroke-width="2" stroke-linejoin="round"/>
    ${eff?`<path d="${eff}" fill="none" stroke="#9CA3AF" stroke-width="1.5" stroke-dasharray="4,3"/>`:''}
    <text x="${pl+cW/2}" y="${H-2}" text-anchor="middle" fill="#9CA3AF" font-size="9">Vazão (m³/h)</text>
    <text x="8" y="${pt+cH/2}" text-anchor="middle" fill="#9CA3AF" font-size="9" transform="rotate(-90,8,${pt+cH/2})">m.c.a</text>
  </svg>`;
}

function openModal(id) {
  const item = ITEMS.find(i => i.id === id);
  if (!item) return;
  document.getElementById('modal-title').textContent = item.nome;
  const specs = Object.entries(item.specs || {});
  document.getElementById('modal-specs').innerHTML =
    specs.map(([k,v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join('') ||
    `<tr><td colspan="2" style="color:var(--muted)">—</td></tr>`;
  document.getElementById('modal-chart').innerHTML = buildChart(item.curva, 300, 180);
  document.getElementById('modal').classList.add('open');
  document.dispatchEvent(new CustomEvent('modal-open', {detail:{id}}));
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
  document.dispatchEvent(new CustomEvent('modal-close'));
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
renderRows('all');
</script>

<!-- Script 2: module — Three.js viewer (vira BimViewer com ssr:false no React) -->
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';

const thumbStates = new Map();
let modalViewer = null;

async function fetchGeo(geoFile) {
  if (geoCache.has(geoFile)) return geoCache.get(geoFile);
  const data = await fetch('./data/' + geoFile).then(r => r.json());
  geoCache.set(geoFile, data);
  return data;
}

function buildScene(data) {
  const scene = new THREE.Scene();
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));
  const hasCol = data.col && data.col.length > 0;
  if (hasCol) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));
  if (data.idx) geom.setIndex(data.idx);
  geom.computeVertexNormals();
  geom.computeBoundingBox();
  const center = geom.boundingBox.getCenter(new THREE.Vector3());
  const size = geom.boundingBox.getSize(new THREE.Vector3()).length();
  const mat = new THREE.MeshStandardMaterial({
    vertexColors: hasCol, color: hasCol ? 0xffffff : 0x8896AA,
    metalness: 0.25, roughness: 0.55,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.position.copy(center.negate());
  scene.add(mesh);
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(2, 3, 2); scene.add(key);
  const fill = new THREE.DirectionalLight(0xC8D8F0, 0.35);
  fill.position.set(-2, 1, -1); scene.add(fill);
  return { scene, size };
}

async function loadThumbnail(id) {
  if (thumbStates.has(id)) return;
  const item = ITEMS.find(i => i.id === id);
  if (!item) return;
  const canvas = document.getElementById('canvas-' + id);
  const loader = document.getElementById('loader-' + id);
  const badge  = document.getElementById('badge-' + id);
  if (!canvas) return;
  thumbStates.set(id, null);
  try {
    const W = canvas.parentElement.offsetWidth || 224;
    const H = canvas.parentElement.offsetHeight || 162;
    const data = await fetchGeo(item.geo);
    const renderer = new THREE.WebGLRenderer({canvas, antialias:false, alpha:false});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setSize(W, H, false);
    renderer.setClearColor(0xF3F4F6, 1);
    const {scene, size} = buildScene(data);
    const camera = new THREE.PerspectiveCamera(38, W/H, 0.001, 500);
    camera.position.set(size*.85, size*.32, size*.85);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    if (loader) loader.style.display = 'none';
    thumbStates.set(id, {renderer, scene, camera, raf: null, animated: false});
    canvas.addEventListener('click', e => {
      e.stopPropagation();
      const st = thumbStates.get(id);
      if (!st || st.animated) return;
      st.animated = true;
      if (badge) badge.classList.add('off');
      const controls = new OrbitControls(camera, canvas);
      controls.autoRotate = true; controls.autoRotateSpeed = 1.2;
      controls.enableDamping = true; controls.dampingFactor = 0.07;
      controls.enableZoom = false; controls.enablePan = false;
      st.controls = controls;
      function animate() {
        if (!thumbStates.has(id)) return;
        st.raf = requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
      }
      animate();
    }, {once: true});
  } catch(e) {
    if (loader) loader.textContent = 'Erro ao carregar';
  }
}

async function initModalViewer(id) {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }
  const item = ITEMS.find(i => i.id === id);
  if (!item) return;
  const canvas = document.getElementById('modal-canvas');
  const W = canvas.parentElement.offsetWidth || 760;
  const H = canvas.parentElement.offsetHeight || 300;
  try {
    const data = await fetchGeo(item.geo);
    const renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:false});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    renderer.setClearColor(0xF3F4F6, 1);
    const {scene, size} = buildScene(data);
    const camera = new THREE.PerspectiveCamera(34, W/H, 0.001, 500);
    camera.position.set(size*.9, size*.35, size*.9);
    camera.lookAt(0, 0, 0);
    const controls = new OrbitControls(camera, canvas);
    controls.autoRotate = true; controls.autoRotateSpeed = 0.7;
    controls.enableDamping = true; controls.dampingFactor = 0.06;
    controls.enableZoom = true; controls.enablePan = false;
    const mv = {renderer, scene, camera, controls, raf: null};
    modalViewer = mv;
    function animate() {
      if (modalViewer !== mv) return;
      mv.raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
  } catch(e) { console.warn('Modal geo error', e); }
}

const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) { loadThumbnail(e.target.dataset.id); io.unobserve(e.target); }
  });
}, {rootMargin: '120px'});

function observeCards() {
  thumbStates.forEach((st, id) => {
    if (!document.getElementById('canvas-' + id)) {
      if (st) { cancelAnimationFrame(st.raf); st.controls?.dispose(); st.renderer?.dispose(); }
      thumbStates.delete(id);
    }
  });
  document.querySelectorAll('.card[data-id]').forEach(card => io.observe(card));
}

document.addEventListener('cards-rendered', () => observeCards());
document.addEventListener('modal-open', e => initModalViewer(e.detail.id));
document.addEventListener('modal-close', () => {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }
});
</script>
</body>
</html>
```

---

### Layout `catalog-grid` — template completo

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ catalog.titulo }} | {{ catalog.fabricante }} | bilds</title>
<meta name="description" content="{{ catalog.descricao }}">
<script type="importmap">{"imports":{"three":"/vendor/three.module.js"}}</script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --orange:#FF4F1F;--blue:#1E40AF;--bg:#F8F9FA;--surface:#fff;
  --text:#111827;--muted:#6B7280;--border:#E5E7EB;--radius:4px;--header:64px;
  font-family:'Inter',system-ui,sans-serif;
}
body{background:var(--bg);color:var(--text);min-height:100vh}

/* Topbar — REMOVER no React */
.topbar{position:sticky;top:0;z-index:100;height:var(--header);background:#fff;
  border-bottom:1px solid var(--border);display:flex;align-items:center;gap:16px;padding:0 24px}
.topbar-logo{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px;text-decoration:none;color:var(--text)}
.topbar-logo svg{color:var(--orange)}
.topbar-sep{color:var(--border);font-size:20px}
.topbar-title{font-size:14px;color:var(--muted)}

/* Hero */
.hero{padding:40px 24px 16px;max-width:1200px;margin:0 auto}
.hero h1{font-family:'Fira Sans',sans-serif;font-size:clamp(20px,3.5vw,30px);font-weight:700;margin-bottom:6px}
.hero-sub{color:var(--muted);font-size:14px}

/* Toolbar: filtros + contagem */
.toolbar{
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:12px 24px 16px;max-width:1200px;margin:0 auto;
}
.chip{padding:6px 14px;border-radius:9999px;border:1px solid var(--border);
  background:#fff;font-size:13px;cursor:pointer;transition:all .15s;white-space:nowrap}
.chip.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.chip:hover:not(.active){border-color:var(--blue);color:var(--blue)}
.toolbar-count{margin-left:auto;font-size:12px;color:var(--muted)}

/* Grid */
.grid-wrap{padding:0 24px 48px;max-width:1200px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}

/* Card */
.card{
  background:var(--surface);border-radius:var(--radius);
  border:1px solid var(--border);cursor:pointer;
  transition:box-shadow .15s,transform .15s;
}
.card:hover{box-shadow:0 4px 16px rgba(0,0,0,.1);transform:translateY(-2px)}
.card-canvas-wrap{position:relative;height:150px;background:#F3F4F6;
  border-radius:var(--radius) var(--radius) 0 0;overflow:hidden}
.card-canvas-wrap canvas{width:100%;height:100%;display:block}
.card-loader{position:absolute;inset:0;display:flex;align-items:center;
  justify-content:center;font-size:11px;color:var(--muted)}
.badge-3d{position:absolute;top:8px;right:8px;width:26px;height:26px;
  background:rgba(255,255,255,.93);border-radius:var(--radius);
  display:flex;align-items:center;justify-content:center;transition:opacity .25s}
.badge-3d svg{width:14px;height:14px;stroke:var(--orange);stroke-width:2;fill:none}
.badge-3d.off{opacity:0;pointer-events:none}
.card-body{padding:10px 12px}
.card-name{font-size:12px;font-weight:600;margin-bottom:3px;line-height:1.3}
.card-meta{font-size:11px;color:var(--muted);margin-bottom:8px}
.card-tag{display:inline-block;font-size:10px;background:#EFF6FF;color:var(--blue);
  border-radius:9999px;padding:2px 8px;margin-bottom:8px}
.card-btn{width:100%;padding:6px;border-radius:var(--radius);
  border:1px solid var(--blue);color:var(--blue);background:#fff;
  font-size:11px;font-weight:600;cursor:pointer;transition:all .15s}
.card-btn:hover{background:var(--blue);color:#fff}

/* Empty state */
.empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:14px}

/* Modal */
.modal-backdrop{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.5);
  backdrop-filter:blur(4px);display:none;align-items:center;
  justify-content:center;padding:16px}
.modal-backdrop.open{display:flex}
.modal{background:#fff;border-radius:var(--radius);width:100%;max-width:780px;
  max-height:92vh;overflow-y:auto;display:flex;flex-direction:column;
  animation:slideUp .2s ease}
@keyframes slideUp{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}
.modal-head{position:sticky;top:0;background:#fff;z-index:10;
  display:flex;align-items:center;gap:12px;padding:16px 20px;
  border-bottom:1px solid var(--border)}
.modal-head h3{font-size:15px;font-weight:600;flex:1}
.modal-close{background:none;border:none;cursor:pointer;padding:4px;
  color:var(--muted);border-radius:var(--radius)}
.modal-close:hover{background:var(--border)}
.modal-3d{height:280px;background:#F3F4F6}
.modal-3d canvas{width:100%;height:100%;display:block}
.modal-body{padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:20px}
.specs-table{font-size:12px;border-collapse:collapse;width:100%}
.specs-table th{text-align:left;font-weight:500;color:var(--muted);padding:4px 0;width:45%}
.specs-table td{padding:4px 0;border-bottom:1px solid var(--border)}
.modal-actions{position:sticky;bottom:0;background:#fff;z-index:10;
  padding:12px 20px;border-top:1px solid var(--border);
  display:flex;gap:8px;justify-content:flex-end}
.btn-primary{background:var(--orange);color:#fff;border:none;border-radius:var(--radius);
  padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer}
.btn-outline{background:#fff;color:var(--muted);border:1px solid var(--border);
  border-radius:var(--radius);padding:8px 18px;font-size:13px;cursor:pointer}

@media(max-width:600px){
  .toolbar,.hero,.grid-wrap{padding-left:16px;padding-right:16px}
  .modal-body{grid-template-columns:1fr}
  .modal-3d{height:220px}
}
</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
</head>
<body>

<!-- Topbar — REMOVER no React -->
<header class="topbar">
  <a class="topbar-logo" href="https://bilds.com">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    bilds
  </a>
  <span class="topbar-sep">/</span>
  <span class="topbar-title">{{ catalog.fabricante }}</span>
</header>

<section class="hero">
  <h1>{{ catalog.titulo }}</h1>
  <p class="hero-sub">{{ catalog.descricao }}</p>
</section>

<div class="toolbar" id="toolbar">
  <button class="chip active" data-filter="all" onclick="filterBy('all',this)">Todos</button>
  {% for f in catalog.filtros %}
  <button class="chip" data-filter="{{ f }}" onclick="filterBy('{{ f }}',this)">{{ f }}</button>
  {% endfor %}
  <span class="toolbar-count" id="count-label"></span>
</div>

<div class="grid-wrap">
  <div class="grid" id="grid-root"></div>
  <div class="empty" id="empty-state" style="display:none">Nenhum produto encontrado.</div>
</div>

<!-- Modal (idêntico ao series-rows) -->
<div class="modal-backdrop" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-head">
      <h3 id="modal-title">—</h3>
      <button class="modal-close" onclick="closeModal()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="modal-3d"><canvas id="modal-canvas"></canvas></div>
    <div class="modal-body">
      <div>
        <h4 style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--muted)">Especificações</h4>
        <table class="specs-table" id="modal-specs"></table>
      </div>
      <div id="modal-chart-wrap">
        <h4 style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--muted)">Curva Q-H</h4>
        <div id="modal-chart"></div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn-outline" onclick="closeModal()">Fechar</button>
      <a class="btn-primary" href="https://bilds.com" target="_blank">Ver na bilds</a>
    </div>
  </div>
</div>

<script>
const CATALOG = {{ catalog | tojson | safe }};
const ITEMS   = CATALOG.produtos;
const geoCache = new Map();
let activeFilter = 'all';

function matchFilter(item, f) { return f==='all' || item.serie===f; }

function buildCard(item) {
  const meta = item.conexoes || (item.potencia ? item.potencia+' CV' : '');
  return `<div class="card" data-id="${item.id}" onclick="openModal('${item.id}')">
    <div class="card-canvas-wrap">
      <canvas id="canvas-${item.id}"></canvas>
      <div class="card-loader" id="loader-${item.id}">Carregando…</div>
      <div class="badge-3d" id="badge-${item.id}">
        <svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
      </div>
    </div>
    <div class="card-body">
      ${item.serie ? `<span class="card-tag">${item.serie}</span>` : ''}
      <div class="card-name">${item.nome}</div>
      ${meta ? `<div class="card-meta">${meta}</div>` : ''}
      <button class="card-btn">Ver detalhes</button>
    </div>
  </div>`;
}

function buildChart(pts) {
  const W=300,H=170;
  if (!pts || !pts.length) return '<p style="font-size:11px;color:var(--muted)">Curva não disponível.</p>';
  const pl=38,pr=10,pt=12,pb=34,cW=W-pl-pr,cH=H-pt-pb;
  const qMax=Math.max(...pts.map(p=>p[0]))*1.1;
  const hMax=Math.max(...pts.map(p=>p[1]))*1.18;
  const tx=q=>pl+(q/qMax)*cW, ty=h=>H-pb-(h/hMax)*cH;
  let g='';
  [.25,.5,.75,1].forEach(f=>{
    const yy=ty(hMax*f).toFixed(1);
    g+=`<line x1="${pl}" y1="${yy}" x2="${W-pr}" y2="${yy}" stroke="#E5E7EB" stroke-width="1"/>`;
    g+=`<text x="${pl-4}" y="${+yy+3}" text-anchor="end" fill="#9CA3AF" font-size="8">${Math.round(hMax*f)}</text>`;
  });
  const path='M'+pts.map(p=>`${tx(p[0]).toFixed(1)},${ty(p[1]).toFixed(1)}`).join('L');
  const area=path+`L${tx(pts.at(-1)[0]).toFixed(1)},${H-pb}L${tx(pts[0][0]).toFixed(1)},${H-pb}Z`;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" xmlns="http://www.w3.org/2000/svg">
    ${g}
    <path d="${area}" fill="rgba(30,64,175,.1)"/>
    <path d="${path}" fill="none" stroke="#1E40AF" stroke-width="2" stroke-linejoin="round"/>
    <text x="${pl+cW/2}" y="${H-2}" text-anchor="middle" fill="#9CA3AF" font-size="8">Vazão (m³/h)</text>
  </svg>`;
}

function renderGrid(filter) {
  activeFilter = filter;
  const filtered = ITEMS.filter(i => matchFilter(i, filter));
  const grid = document.getElementById('grid-root');
  const empty = document.getElementById('empty-state');
  const label = document.getElementById('count-label');
  if (!filtered.length) {
    grid.innerHTML = '';
    empty.style.display = 'block';
  } else {
    grid.innerHTML = filtered.map(buildCard).join('');
    empty.style.display = 'none';
  }
  if (label) label.textContent = `${filtered.length} produto${filtered.length !== 1 ? 's' : ''}`;
  document.dispatchEvent(new CustomEvent('cards-rendered', {detail:{filter}}));
}

function filterBy(f, el) {
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  renderGrid(f);
}

function openModal(id) {
  const item = ITEMS.find(i => i.id === id);
  if (!item) return;
  document.getElementById('modal-title').textContent = item.nome;
  const specs = Object.entries(item.specs || {});
  document.getElementById('modal-specs').innerHTML =
    specs.map(([k,v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join('') ||
    `<tr><td colspan="2" style="color:var(--muted)">—</td></tr>`;
  document.getElementById('modal-chart').innerHTML = buildChart(item.curva);
  document.getElementById('modal').classList.add('open');
  document.dispatchEvent(new CustomEvent('modal-open', {detail:{id}}));
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
  document.dispatchEvent(new CustomEvent('modal-close'));
}

document.addEventListener('keydown', e => { if (e.key==='Escape') closeModal(); });
renderGrid('all');
</script>

<!-- Three.js — idêntico ao series-rows, só muda fetch path e dimensões do canvas -->
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';

const thumbStates = new Map();
let modalViewer = null;

async function fetchGeo(geo) {
  if (geoCache.has(geo)) return geoCache.get(geo);
  const data = await fetch('./data/' + geo).then(r => r.json());
  geoCache.set(geo, data);
  return data;
}

function buildScene(data) {
  const scene = new THREE.Scene();
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));
  const hasCol = data.col && data.col.length > 0;
  if (hasCol) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));
  if (data.idx) geom.setIndex(data.idx);
  geom.computeVertexNormals();
  geom.computeBoundingBox();
  const center = geom.boundingBox.getCenter(new THREE.Vector3());
  const size = geom.boundingBox.getSize(new THREE.Vector3()).length();
  const mat = new THREE.MeshStandardMaterial({
    vertexColors: hasCol, color: hasCol ? 0xffffff : 0x8896AA,
    metalness: 0.25, roughness: 0.55,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.position.copy(center.negate());
  scene.add(mesh);
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(2,3,2); scene.add(key);
  const fill = new THREE.DirectionalLight(0xC8D8F0, 0.35);
  fill.position.set(-2,1,-1); scene.add(fill);
  return {scene, size};
}

async function loadThumbnail(id) {
  if (thumbStates.has(id)) return;
  const item = ITEMS.find(i => i.id === id);
  if (!item) return;
  const canvas = document.getElementById('canvas-' + id);
  const loader = document.getElementById('loader-' + id);
  const badge  = document.getElementById('badge-' + id);
  if (!canvas) return;
  thumbStates.set(id, null);
  try {
    const W = canvas.parentElement.offsetWidth || 200;
    const H = canvas.parentElement.offsetHeight || 150;
    const data = await fetchGeo(item.geo);
    const renderer = new THREE.WebGLRenderer({canvas, antialias:false, alpha:false});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setSize(W, H, false);
    renderer.setClearColor(0xF3F4F6, 1);
    const {scene, size} = buildScene(data);
    const camera = new THREE.PerspectiveCamera(38, W/H, 0.001, 500);
    camera.position.set(size*.85, size*.32, size*.85);
    camera.lookAt(0,0,0);
    renderer.render(scene, camera);
    if (loader) loader.style.display = 'none';
    thumbStates.set(id, {renderer, scene, camera, raf:null, animated:false});
    canvas.addEventListener('click', e => {
      e.stopPropagation();
      const st = thumbStates.get(id);
      if (!st || st.animated) return;
      st.animated = true;
      if (badge) badge.classList.add('off');
      const controls = new OrbitControls(camera, canvas);
      controls.autoRotate = true; controls.autoRotateSpeed = 1.2;
      controls.enableDamping = true; controls.dampingFactor = 0.07;
      controls.enableZoom = false; controls.enablePan = false;
      st.controls = controls;
      function animate() {
        if (!thumbStates.has(id)) return;
        st.raf = requestAnimationFrame(animate);
        controls.update(); renderer.render(scene, camera);
      }
      animate();
    }, {once:true});
  } catch(e) {
    if (loader) loader.textContent = 'Erro';
  }
}

async function initModalViewer(id) {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }
  const item = ITEMS.find(i => i.id === id);
  if (!item) return;
  const canvas = document.getElementById('modal-canvas');
  const W = canvas.parentElement.offsetWidth || 760;
  const H = canvas.parentElement.offsetHeight || 280;
  try {
    const data = await fetchGeo(item.geo);
    const renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:false});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    renderer.setClearColor(0xF3F4F6, 1);
    const {scene, size} = buildScene(data);
    const camera = new THREE.PerspectiveCamera(34, W/H, 0.001, 500);
    camera.position.set(size*.9, size*.35, size*.9);
    camera.lookAt(0,0,0);
    const controls = new OrbitControls(camera, canvas);
    controls.autoRotate = true; controls.autoRotateSpeed = 0.7;
    controls.enableDamping = true; controls.dampingFactor = 0.06;
    controls.enableZoom = true; controls.enablePan = false;
    const mv = {renderer, scene, camera, controls, raf:null};
    modalViewer = mv;
    function animate() {
      if (modalViewer !== mv) return;
      mv.raf = requestAnimationFrame(animate);
      controls.update(); renderer.render(scene, camera);
    }
    animate();
  } catch(e) { console.warn('Modal error', e); }
}

const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) { loadThumbnail(e.target.dataset.id); io.unobserve(e.target); }
  });
}, {rootMargin:'120px'});

function observeCards() {
  thumbStates.forEach((st, id) => {
    if (!document.getElementById('canvas-'+id)) {
      if (st) { cancelAnimationFrame(st.raf); st.controls?.dispose(); st.renderer?.dispose(); }
      thumbStates.delete(id);
    }
  });
  document.querySelectorAll('.card[data-id]').forEach(c => io.observe(c));
}

document.addEventListener('cards-rendered', () => observeCards());
document.addEventListener('modal-open', e => initModalViewer(e.detail.id));
document.addEventListener('modal-close', () => {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }
});
</script>
</body>
</html>
```

---

## 9. O que NÃO alterar

- Schema de `libraryFiles` na Company — campo separado para downloads de `.aq`
- Rotas estáticas de `[customLink]/` existentes (`editar`, `avaliacoes`, `seguir`, etc.)
- Qualquer componente fora do escopo BIM — não refatorar nada além do que está listado acima
- Configurações de deploy, vercel.json, CI/CD existentes
- Padrões de autenticação/guard — reutilizar os existentes sem modificar

---

## 10. Pontos críticos que causam bloqueio ou retrabalho

Leia esta seção antes de começar — cada item aqui representa um erro que custaria horas de diagnóstico se descoberto tarde.

### 10.1 CORS no S3/CloudFront para os geo JSONs

O browser vai fazer `fetch('https://storage.bilds.com/b-bim-3d/.../geo/cam-w10.json')` a partir da página em `bilds.com`. Isso é cross-origin. Se o bucket S3 (ou distribuição CloudFront) não tiver a política CORS correta, o fetch falha silenciosamente no browser.

**Antes de testar o viewer**, adicione a política CORS ao bucket S3 que serve os arquivos BIM:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET"],
    "AllowedOrigins": ["https://bilds.com", "https://*.bilds.com"],
    "ExposeHeaders": []
  }
]
```

E na distribuição CloudFront, configure o comportamento para repassar o header `Origin` e incluir `Access-Control-Allow-Origin` na resposta.

### 10.2 Biblioteca ZIP para o NestJS

O endpoint `POST /companies/:id/b-bim-3d` precisa extrair o ZIP em memória. O Node.js não tem extração de ZIP nativa. Instale uma das opções abaixo no workspace da API:

```bash
pnpm add adm-zip --filter <workspace-api>   # síncrono, simples
# ou
pnpm add unzipper --filter <workspace-api>  # stream-based, async
```

Leia o `package.json` da API para encontrar o nome correto do workspace antes de rodar o comando.

Exemplo com `adm-zip`:
```typescript
import AdmZip from 'adm-zip'

const zip = new AdmZip(file.buffer)        // file.buffer vem do multer/interceptor
const manifest = JSON.parse(zip.readAsText('manifest.json'))
const catalog = JSON.parse(zip.readAsText('catalog.json'))
const geoEntries = zip.getEntries().filter(e => e.entryName.startsWith('geo/'))
```

### 10.3 Import path do OrbitControls via npm

Desde Three.js r152 (2023), o caminho de import do OrbitControls mudou. Use o caminho novo, não o antigo:

```typescript
// ✅ correto (r152+)
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

// ❌ antigo — quebra com versões recentes do three
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
```

Verifique a versão do `three` que será instalada (`pnpm add three`) e confirme qual caminho é o correto para ela.

### 10.4 React + Three.js: padrões obrigatórios

**Cleanup no unmount** — sem isso, múltiplos contextos WebGL acumulam e a GPU trava:

```typescript
useEffect(() => {
  const renderer = new THREE.WebGLRenderer({ canvas: canvasRef.current })
  // ... setup
  const raf = requestAnimationFrame(animate)
  return () => {                         // ← cleanup obrigatório
    cancelAnimationFrame(raf)
    controls.dispose()
    renderer.dispose()
  }
}, [geoUrl])                             // re-executa quando o produto muda
```

**`geoCache` em nível de módulo** — não use `useState` nem `useRef` para o cache. Declare fora do componente para que persista entre re-renders e seja compartilhado entre thumbnail e modal:

```typescript
// fora do componente — correto
const geoCache = new Map<string, GeoData>()

export function BimViewer(...) { /* usa geoCache */ }
```

**Canvas sizing via ref, não parentElement** — `offsetWidth` retorna 0 antes do layout. Use:

```typescript
useEffect(() => {
  const canvas = canvasRef.current
  const W = canvas.offsetWidth || canvas.parentElement?.offsetWidth || 224
  const H = canvas.offsetHeight || canvas.parentElement?.offsetHeight || 162
  // ...
}, [])
```

**IntersectionObserver em React** — não use `document.querySelector` após re-render. Use refs:

```typescript
const cardRefs = useRef<Map<string, HTMLElement>>(new Map())

useEffect(() => {
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        const id = (e.target as HTMLElement).dataset.id!
        loadThumbnail(id)
        io.unobserve(e.target)
      }
    })
  }, { rootMargin: '120px' })

  cardRefs.current.forEach(el => io.observe(el))
  return () => io.disconnect()
}, [filteredItems])  // re-observa quando o filtro muda
```

### 10.5 `BimViewer` tem dois modos distintos

O componente serve propósitos diferentes em thumbnail e modal. Implemente com uma prop `mode`:

| Prop `mode` | Comportamento |
|---|---|
| `'thumbnail'` | 1 frame estático. Click ativa OrbitControls + loop. `antialias:false`, `pixelRatio: min(dpr, 1.5)`. Canvas ~200×150px. `enableZoom:false`. |
| `'modal'` | Loop contínuo desde o início. `antialias:true`, `pixelRatio: min(dpr, 2)`. Canvas ~760×280px. `enableZoom:true`. |

```typescript
<BimViewer geoUrl={geoBaseUrl + product.geo} mode="thumbnail" />
<BimViewer geoUrl={geoBaseUrl + selectedProduct.geo} mode="modal" />
```

Ambos os modos usam `dynamic(() => import('./BimViewer'), { ssr: false })`.

### 10.6 `geoBaseUrl` sempre termina com `/`

A concatenação de URL para buscar geometria é sempre:
```
geoBaseUrl + produto.geo
= "https://storage.bilds.com/b-bim-3d/dancor/bombas-incendio/geo/" + "cam-w10.json"
= "https://storage.bilds.com/b-bim-3d/dancor/bombas-incendio/geo/cam-w10.json"
```

Garanta que ao salvar `geoBaseUrl` no MongoDB e ao fazer upload no S3, a barra final esteja presente. Valide isso no Zod schema do endpoint.

### 10.7 Relação `filtros` ↔ `item.serie`

Os chips de filtro usam os valores de `catalog.filtros[]`. O filtro ativo compara com `produto.serie`. A relação é direta:

```typescript
// chip com value "CAM-W" filtra produtos onde produto.serie === "CAM-W"
const filtered = produtos.filter(p => activeFilter === 'all' || p.serie === activeFilter)
```

Se `catalog.filtros` for `[]`, renderize só o chip "Todos" sem nenhum filtro adicional.

### 10.8 Verifique as rotas existentes em `[customLink]/` antes de criar `[catalogSlug]`

Liste os arquivos em `apps/web/src/app/[customLink]/` (ou onde fica essa rota no codebase). Se existir um `page.tsx` no próprio `[customLink]/`, ele é a página de empresa. Se existirem pastas estáticas (`editar/`, `avaliacoes/`, etc.), elas têm prioridade sobre `[catalogSlug]`. Confirme que não há slug de catálogo que conflite com uma rota estática existente.

### 10.9 Nome do workspace para `pnpm add`

O comando `pnpm add three @types/three --filter <workspace>` requer o nome correto do package. Leia o `package.json` do app web antes de rodar:

```bash
cat apps/web/package.json | grep '"name"'
# depois:
pnpm add three @types/three --filter <nome-encontrado>
```

### 10.10 Página de empresa existente — não quebrar

O `[customLink]/page.tsx` provavelmente já exibe uma seção de arquivos `.aq` para download (campo `libraryFiles` da Company). Essa seção **não deve ser alterada**. Se quiser adicionar um link para o catálogo BIM interativo na página de empresa, faça isso de forma aditiva — um novo bloco abaixo da seção existente, sem tocar no código existente da seção `libraryFiles`.

---

## 11. Referência rápida — URLs de exemplo após implementação

```
Dashboard:
  dashboard.bilds.com/b-bim-3d                        ← grid de empresas
  dashboard.bilds.com/b-bim-3d/{company-id}           ← gerenciar catálogos
  dashboard.bilds.com/b-bim-3d/{company-id}/novo      ← formulário de upload

API:
  POST   /companies/{id}/b-bim-3d            ← upload ZIP
  PATCH  /companies/{id}/b-bim-3d/{slug}     ← trocar layout

bilds.com:
  bilds.com/dancor/bombas-incendio               ← página pública SSR

S3 / CloudFront:
  storage.bilds.com/b-bim-3d/dancor/bombas-incendio/catalog.json
  storage.bilds.com/b-bim-3d/dancor/bombas-incendio/geo/cam-w10.json
```
