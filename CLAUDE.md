# CLAUDE.md — bilds-bim-3d

Ponto de entrada para qualquer agente ou humano que trabalhe neste projeto.
Leia tudo antes de modificar qualquer arquivo.

---

## Skills obrigatórias — carregar ao iniciar

Ao começar qualquer sessão neste projeto, carregue as três skills abaixo antes de qualquer outra ação:

- `leitor-biblioteca-aq`
- `leitor-ifc`
- `pagina-biblioteca`

Invoque via Skill tool em paralelo.

---

## O que é este projeto

Pipeline local para gerar catálogos BIM interativos com viewer 3D a partir de
arquivos `.aq` (AltoQi) e `.IFC` (geometria). Produz dois artefatos:

1. **Preview HTML standalone** (`output/preview/`) — visualização local ou via Vercel
2. **ZIP para bilds.com** (`output/bilds-upload.zip`) — pacote para upload no dashboard

O projeto é independente do `bilds-code-vercel` (apps/lps, vagas, seo).
Clonado em qualquer máquina, produz o mesmo resultado dado os mesmos inputs.

---

## Fluxo do usuário

```
1. Clonar este repo
2. Rodar: bash scripts/setup_vendor.sh  (baixa Three.js para templates/vendor/)
3. pip install -r requirements.txt      (instala Jinja2)
4. Copiar arquivos .IFC e .aq para input/
5. Copiar config.example.json → config.json, editar com seus dados
6. python3 scripts/build.py --config config.json
7. Preview local: python3 -m http.server 8080 --directory output/preview
8. Abrir: http://localhost:8080
9. Subir output/bilds-upload.zip no dashboard.bilds.com → BIM 3D
```

---

## Estrutura do projeto

```
bilds-bim-3d/
├── CLAUDE.md                    ← você está aqui
├── README.md                    ← guia para o usuário final
├── config.example.json          ← template de configuração
├── config.json                  ← criado pelo usuário, gitignored
├── requirements.txt             ← Jinja2
├── vercel.json                  ← serve output/preview/ como site estático
├── scripts/
│   ├── build.py                 ← pipeline principal (entry point)
│   ├── parse_ifc.py             ← IFC4 → JSON de geometria
│   ├── read_aq.py               ← .aq AltoQi → dados de produto
│   ├── dedup.py                 ← deduplicação de vértices (80% redução)
│   └── setup_vendor.sh          ← baixa Three.js para templates/vendor/
├── templates/
│   ├── layouts/
│   │   ├── series-rows.html     ← layout Dancor: rows Netflix por série
│   │   └── catalog-grid.html   ← layout Amanco: grid denso com filtros
│   └── vendor/                  ← Three.js self-hosted (gitignored após setup)
├── input/                       ← arquivos do usuário (.IFC, .aq) — gitignored
└── output/                      ← gerado pelo build — geo/ e *.json gitignored
    ├── geo/                     ← JSONs de geometria por produto
    ├── catalog.json             ← dados estruturados do catálogo
    ├── preview/                 ← site estático pronto para servir
    └── bilds-upload.zip         ← ZIP para bilds.com
```

---

## config.json — schema completo

```json
{
  "slug":        "bombas-incendio",
  "titulo":      "Bombas de Combate a Incêndio",
  "fabricante":  "Dancor",
  "descricao":   "Linha CAM-W e TJM para sistemas de combate a incêndio.",
  "layout":      "series-rows",
  "aq_file":     "input/pecas_dancor.aq",
  "ifc_dir":     "input/",
  "file_map": {
    "CAM-W10.IFC": "cam-w10",
    "CAM-W14.IFC": "cam-w14"
  },
  "products_override": [
    {
      "id": "89-62",
      "nome": "CAM 89-62 TJM 50CV",
      "serie": "TJM",
      "geo": "cam-89-62-tjm",
      "potencia": 50,
      "conexoes": "2½\" × 2½\"",
      "specs": { "Tensão": "Trifásico 220/380V", "Rotação": "3.500 rpm · 60Hz" },
      "curva": null
    }
  ]
}
```

`products_override`: produtos presentes nos IFCs mas ausentes no .aq.
`file_map`: mapeamento nome-exato-do-arquivo.IFC → slug-de-saída.

---

## catalog.json — schema de saída

```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "fabricante": "Dancor",
  "descricao": "...",
  "layout": "series-rows",
  "filtros": ["W", "TJM"],
  "produtos": [
    {
      "id": "cam-w10",
      "nome": "CAM-W10 1CV T 220/380V INC FLG IR3",
      "serie": "W",
      "geo": "cam-w10.json",
      "potencia": 1.0,
      "conexoes": "1½\" × 1½\"",
      "specs": { "Tensão": "Trifásico 220/380V", "Rotação": "3.500 rpm · 60Hz" },
      "curva": [[0,30,1.1,0],[3,25,1.2,42],[6,18,1.3,58],[9,8,1.2,48]]
    }
  ]
}
```

`curva`: lista de [vazao_m3h, altura_mca, potencia_cv, rendimento_%] por ponto.
`curva: null` para produtos sem curva Q-H.

---

## Layouts disponíveis

| Layout | Arquivo | Quando usar |
|---|---|---|
| `series-rows` | `templates/layouts/series-rows.html` | Poucas séries (2–4), muitas variantes, produto com curva Q-H. Ex: Dancor |
| `catalog-grid` | `templates/layouts/catalog-grid.html` | Muitos itens heterogêneos (20+), filtros por categoria. Ex: Amanco |

Para adicionar um novo layout:
1. Criar `templates/layouts/meu-layout.html` usando os mesmos padrões (ver seção abaixo)
2. Usar `"layout": "meu-layout"` no config.json

### Padrão obrigatório nos templates

Os templates usam **dois scripts** para resolver o timing do Three.js:

- **Script sync** (inline, sem `type="module"`): renderiza cards no DOM,
  dispara `CustomEvent('cards-rendered')` ao terminar.
- **Script module** (`type="module"`): importa Three.js, ouve o evento,
  acessa os `<canvas>` que já existem no DOM.

O importmap **deve vir antes** de qualquer `<script type="module">`:
```html
<script type="importmap">{"imports":{"three":"/vendor/three.module.js"}}</script>
```

Dados injetados via Jinja2:
```html
<script>
const CATALOG = {{ catalog | tojson | safe }};
const ITEMS   = CATALOG.produtos;
</script>
```

Fallback sem Jinja2: `build.py` substitui `{{ catalog | tojson | safe }}` por string literal.

---

## ZIP para bilds.com — conteúdo

```
bilds-upload.zip
├── manifest.json    { slug, titulo, fabricante, descricao, layout, filtros, n_produtos }
├── catalog.json     dados completos dos produtos
└── geo/
    ├── cam-w10.json
    └── cam-w14.json
    ...
```

O dashboard.bilds.com lê `manifest.json` para exibir o nome/slug antes de processar
o zip inteiro. `catalog.json` e `geo/*.json` vão para S3, registrados no MongoDB.

---

## Conhecimento crítico: parse_ifc.py

### O bug mais comum — IFCLOCALPLACEMENT ignorado

Parsers ingênuos aplicam só `IFCCARTESIANTRANSFORMATIONOPERATOR3D` (identidade em
muitos exportadores) e ignoram `IFCLOCALPLACEMENT`. Resultado: cada sub-peça renderiza
na sua origem local — motor, voluta e flanges aparecem separados por metros.

**A transform correta:**
```
v_world = T_LP_hierarquia × T_mapping_target × inv(T_mapping_origin) × v_local
```
Na maioria dos exportadores CAD: T_mapping_target = T_mapping_origin = identidade.
Então: `v_world = T_LP × v_local`

`resolve_lp()` em `parse_ifc.py` acumula a hierarquia recursivamente com cache.

### Dois caminhos de geometria (Caminho A e B)

**A — face set direto:**
```
IFCBUILDINGELEMENTPROXY → IFCPRODUCTDEFINITIONSHAPE →
  IFCSHAPEREPRESENTATION (Tessellation) → IFCTRIANGULATEDFACESET
```

**B — instância compartilhada (peças repetidas):**
```
IFCBUILDINGELEMENTPROXY → IFCPRODUCTDEFINITIONSHAPE →
  IFCSHAPEREPRESENTATION (MappedRepresentation) →
    IFCMAPPEDITEM
      MappingSource → IFCREPRESENTATIONMAP → IFCTRIANGULATEDFACESET
      MappingTarget → IFCCARTESIANTRANSFORMATIONOPERATOR3D
```

### IFCAXIS2PLACEMENT3D → Matriz 4×4

```
Z = normalize(Axis)
X = normalize(RefDirection − (RefDirection·Z)·Z)
Y = cross(Z, X)

M (row-major) =
  [ Xx  Yx  Zx  Tx ]
  [ Xy  Yy  Zy  Ty ]
  [ Xz  Yz  Zz  Tz ]
  [  0   0   0   1 ]
```

### Conversão de eixos: IFC (Z-up) → Three.js (Y-up)

```python
THREE_x =  v[0]
THREE_y =  v[2]   # Z do IFC vira Y no Three.js
THREE_z = -v[1]   # Y do IFC inverte e vira Z
```

### split_top() — obrigatório para formato STEP

`split(',')` simples quebra strings STEP com vírgulas internas como
`'MOTOR WEG 3,0CV T 220V'`. Usar sempre `split_top()` que respeita
profundidade de parênteses e strings.

### IFCINDEXEDCOLOURMAP — cores por face

Entidades standalone no arquivo IFC, não filhas de nenhuma outra.
A ligação vai do mapa para o face set, não o contrário.

```
IFCCOLOURRGBLIST(((r,g,b),(r,g,b),...))
IFCINDEXEDCOLOURMAP(FaceSetRef, Opacity, ColourRGBListRef, ColourIndex)
```
`ColourIndex[i]` (1-based) = índice da cor na paleta para o triângulo `i`.

Quando há IFCINDEXEDCOLOURMAP: emitir triângulos expandidos (sem compartilhar
vértices) para que cada vértice tenha a cor correta. O dedup.py depois compacta.

### Armadilha: unidades

Alguns exportadores (CATIA) declaram `MILLIMETRE` mas escrevem em metros.
Verificar a magnitude: coordenadas industriais em metros ficam em 0.01–5.0.
Se estiver em 10–5000, realmente está em mm — dividir por 1000.

### Filtrar vértices outlier

Alguns exportadores produzem IFCLOCALPLACEMENT aberrante (translação de 5m, 16m)
em sub-componentes. O parser aplica corretamente — o problema está nos dados.
Identificar pelo bounding box do JSON e filtrar com threshold por tipo de equipamento:
- Bomba compacta: 3m
- Válvula/fitting: 2m
- Equipamento grande (chiller): 10m

---

## Conhecimento crítico: read_aq.py

### .aq pode ser ZIP ou SQLite direto

Sempre tentar SQLite direto primeiro (alguns .aq são extraídos de outro ZIP).
Encoding: `latin-1` (Windows-1252) — **sempre** configurar antes de qualquer query.

### Tabelas principais

- `GRUPO_PECA` — séries/famílias (NOME_GP = "CAM-W10", "CAM-W21")
- `PECA` — variantes individuais (NOME_PECA, DESCRICAO_DADOS)
- `DADOS_HIDRAULICOS` — parâmetros hidráulicos por peça
- `MODELO_BOMBA` — nome e potência nominal do modelo
- `ITEM_CURVA_BOMBA` — pontos Q-H (VAZAO_ICB, ALTURA_ICB, POTENCIA_ICB, RENDIMENTO_ICB)
- `PROPRIEDADE_PERSONALIZADA` / `VALOR_PROPRIEDADE_PERSONALIZADA` — specs livres

### Propriedades observadas em bombas

Tensão, Corrente, Grau de Proteção, Isolamento, Sucção x Recalque,
Altura Máxima, Temperatura máxima, Motor, Rotor, Rotação.

---

## Conhecimento crítico: templates HTML

### Three.js self-hosted — obrigatório

CSP da Vercel bloqueia `cdn.jsdelivr.net`, `unpkg.com`, `cdnjs.cloudflare.com`
silenciosamente. Sempre self-host em `templates/vendor/` e copiar para `output/preview/vendor/`.

### Padrão de thumbnail estática + click-to-3D

Não inicializar todos os viewers simultaneamente — GPU explode com 10+ contextos WebGL.
- `IntersectionObserver` com `rootMargin:'120px'` para lazy load
- `renderer.render()` uma vez → thumbnail estática
- OrbitControls + loop de animação só ao clicar

### Cache de geometria

```javascript
const geoCache = new Map(); // filename → data
async function fetchGeo(geo) {
  if (geoCache.has(geo)) return geoCache.get(geo);
  const data = await fetch('./data/' + geo).then(r => r.json());
  geoCache.set(geo, data); return data;
}
```

Quando o modal abre, o JSON já está em memória se o thumbnail foi carregado.

### vertexColors no Three.js

```javascript
const hasCol = data.col && data.col.length > 0;
const mat = new THREE.MeshStandardMaterial({
  vertexColors: hasCol,
  color: hasCol ? 0xffffff : 0x8896AA,  // branca com vertexColors (multiplicação), cinza sem
});
if (data.idx) geom.setIndex(data.idx);  // guard — ausente em geo expandida
```

### Design tokens bilds.com

```css
--orange: #FF4F1F   /* só em botão CTA primário */
--blue:   #1E40AF   /* botão secundário, link */
--radius: 4px       /* universal; badge é exceção: 9999px */
```
Fontes: **Fira Sans** (título de seção, hero) + **Inter** (todo o resto).
Ícones: Lucide SVG, stroke 2px, outline, currentColor.
Sombra: só no hover de cards clicáveis. Cards sem borda de hover por padrão.

---

## Integração com bilds.com (fase 2 — não implementada neste repo)

O ZIP gerado por este projeto será consumido por:

**dashboard.bilds.com** (`bilds.com/apps/admin`):
- Menu item "BIM 3D" em `src/components/Menu/menuConfig.tsx`
- Rotas: `/bim-3d` (grid de empresas), `/bim-3d/[companyId]/novo` (upload)
- Stack: Next.js 16, RTK Query, react-dropzone, react-hook-form + zod

**API NestJS** (`bilds.com/apps/api`):
- `POST /companies/:id/bim-catalogs` — recebe ZIP, extrai, salva no S3
- MongoDB Company: novo campo `bimCatalogs: BimCatalog[]`
- Storage: S3 + CloudFront (`S3Service`, `AWS_CLOUD_FRONT_BASE_URL`)

**bilds.com web** (`bilds.com/apps/web`):
- Rota `app/[customLink]/[catalogSlug]/page.tsx` — Server Component
- `generateMetadata()` lê `catalog.json` do S3 para SEO (title, description)
- `ProductGrid` renderizado server-side (SSR — indexável por crawlers)
- `BimViewer` React com `three` via npm, `dynamic(() => ..., {ssr:false})`

**Seleção de layout no dashboard:**
- Campo `layout` gravado no MongoDB (não no catalog.json)
- Admin pode trocar o layout sem re-upload dos arquivos
- Seletor visual com SVGs wireframe por layout no formulário

---

## Diagnóstico rápido de problemas

| Sintoma | Causa provável |
|---|---|
| Peças separadas por metros | resolve_lp() não acumula hierarquia recursivamente |
| Fragmentos a 5–16m do corpo | LP aberrante no IFC exportado — filtrar outliers |
| Modelo ~1000× maior | Conversão mm→m desnecessária — verificar magnitude das coordenadas brutas |
| Modelo cinza (tem cores no IFC) | build_face_color_map() não chamado, ou IFCINDEXEDCOLOURMAP não encontrado |
| 0 cores do IFCCOLOURRGBLIST | Regex espera inteiros mas floats têm casas decimais |
| `col[]` presente mas Three.js ignora | Material sem `vertexColors: true` ou `color` não é 0xffffff |
| `import * as THREE from 'three'` falha | importmap ausente ou fora de ordem no HTML |
| Canvas não encontrado no init | Módulo rodou antes de 'cards-rendered' — verificar handshake |
| GPU trava | Loop de animação em todos os cards — thumbnail estática + loop só no click |
| ZIP vazio de geo files | IFCs não foram parseados — verificar output/geo/ após o build |
| .aq não abre como SQLite | Tentar abrir como ZIP; se falhar: arquivo corrompido |
| Texto com lixo | Encoding não configurado — usar `latin-1` |

---

## Git e deploy

**Identidade:** commits neste repo usam `carlosnetoaltoqi`.
Verificar com `git config user.name` e `git config user.email`.
Se necessário: `git config user.name "carlosnetoaltoqi"`

**output/preview/** NÃO é gitignored (é o artefato de preview commitado).
**output/geo/** e **output/*.json** SÃO gitignored (gerado localmente).

**Preview via Vercel:** `vercel deploy output/preview/ --prod`
O `vercel.json` na raiz do repo já está configurado para servir `output/preview/`.

**Preview local:**
```bash
python3 -m http.server 8080 --directory output/preview
```
