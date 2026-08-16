# Plano de integração: bilds-bim-3d → bilds.com

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

Adicione o subdocumento `bimCatalogs` ao schema de Company existente. **Não altere campos existentes** (`libraryFiles`, `name`, `customLink`, etc.).

```typescript
// Novo subdocumento
class BimCatalog {
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
bimCatalogs: BimCatalog[];   // padrão: []
```

O `catalogUrl` aponta para onde o catalog.json completo está no CloudFront:
```
https://{CLOUDFRONT_BASE}/bim/{slug-empresa}/{slug-catalogo}/catalog.json
```

O `geoBaseUrl` é o prefixo base dos arquivos de geometria:
```
https://{CLOUDFRONT_BASE}/bim/{slug-empresa}/{slug-catalogo}/geo/
```

Para carregar a geometria de um produto: `geoBaseUrl + produto.geo`
Ex: `https://storage.bilds.com/bim/dancor/bombas-incendio/geo/cam-w10.json`

---

## 4. API NestJS — endpoint de upload

```
POST /companies/:id/bim-catalogs
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
   bim/{customLink-da-empresa}/{manifest.slug}/geo/{nome-arquivo}
   ```
4. Fazer upload do `catalog.json` para S3:
   ```
   bim/{customLink-da-empresa}/{manifest.slug}/catalog.json
   ```
5. Construir URLs do CloudFront usando `process.env.AWS_CLOUD_FRONT_BASE_URL`
6. Upsert em `company.bimCatalogs` (slug é chave — se já existe, atualiza; se não, insere)
7. Retornar o `BimCatalog` salvo

**Resposta:**
```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "catalogUrl": "https://storage.bilds.com/bim/dancor/bombas-incendio/catalog.json",
  "geoBaseUrl": "https://storage.bilds.com/bim/dancor/bombas-incendio/geo/",
  "publishedAt": "2026-08-16T00:00:00.000Z",
  "active": true
}
```

**Endpoint adicional para trocar layout sem re-upload:**
```
PATCH /companies/:id/bim-catalogs/:slug
Body: { layout: 'series-rows' | 'catalog-grid' }
```

Esse endpoint só atualiza o campo `layout` no banco — sem alterar os arquivos no S3.

---

## 5. Dashboard — menu e interface de upload

### 5.1 Novo item no menu lateral

Adicione "BIM 3D" como item de menu em `dashboard.bilds.com`. O ícone sugerido é `Box` ou `Package` do Lucide. A rota pode ser `/bim`.

### 5.2 Página `/bim` — grid de empresas

Lista as empresas que têm `bimCatalogs.length > 0`. Use o padrão de grid existente no dashboard. Cada card mostra:
- Nome da empresa
- Número de catálogos publicados
- Botão "Gerenciar" → `/bim/{company-id}`

### 5.3 Página `/bim/{company-id}` — gerenciamento por empresa

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
2. Encontra o `BimCatalog` pelo `catalogSlug` dentro de `company.bimCatalogs`
3. Faz `fetch(catalog.catalogUrl)` para obter o `catalog.json` completo com os produtos
4. Retorna `{ company, catalog, catalogData }`

### 6.3 Componentes React necessários

Crie dentro de `apps/web/src/components/bim/` (ou onde o codebase organiza componentes):

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

1. **MongoDB**: adicionar `bimCatalogs: BimCatalog[]` ao schema de Company
2. **API**: endpoint `POST /companies/:id/bim-catalogs` com extração do ZIP e upload S3
3. **API**: endpoint `PATCH /companies/:id/bim-catalogs/:slug` (troca de layout)
4. **Dashboard**: menu "BIM 3D" + páginas de listagem e upload
5. **bilds.com web**: rota `[customLink]/[catalogSlug]` com stub (mostra título + fabricante)
6. **Componentes**: `CurveChart` (SVG, sem dependência externa)
7. **Componentes**: `SeriesRowsLayout` e `CatalogGridLayout` com cards estáticos
8. **Componentes**: `BimViewer` com Three.js (instalar `three` no workspace)
9. **Componentes**: `ProductModal` conectando viewer + curva + specs
10. **SEO**: `generateMetadata` completo
11. Teste end-to-end com ZIP real

---

## 9. O que NÃO alterar

- Schema de `libraryFiles` na Company — campo separado para downloads de `.aq`
- Rotas estáticas de `[customLink]/` existentes (`editar`, `avaliacoes`, `seguir`, etc.)
- Qualquer componente fora do escopo BIM — não refatorar nada além do que está listado acima
- Configurações de deploy, vercel.json, CI/CD existentes
- Padrões de autenticação/guard — reutilizar os existentes sem modificar

---

## 10. Referência rápida — URLs de exemplo após implementação

```
Dashboard:
  dashboard.bilds.com/bim                        ← grid de empresas
  dashboard.bilds.com/bim/{company-id}           ← gerenciar catálogos
  dashboard.bilds.com/bim/{company-id}/novo      ← formulário de upload

API:
  POST   /companies/{id}/bim-catalogs            ← upload ZIP
  PATCH  /companies/{id}/bim-catalogs/{slug}     ← trocar layout

bilds.com:
  bilds.com/dancor/bombas-incendio               ← página pública SSR

S3 / CloudFront:
  storage.bilds.com/bim/dancor/bombas-incendio/catalog.json
  storage.bilds.com/bim/dancor/bombas-incendio/geo/cam-w10.json
```
