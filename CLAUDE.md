# CLAUDE.md — bilds-bim-3d

Ponto de entrada para qualquer agente ou humano que trabalhe neste projeto.
Leia tudo antes de modificar qualquer arquivo.

---

## Regra fundamental: documentação primeiro

**Toda mudança de comportamento, bug corrigido ou decisão de arquitetura deve ser registrada neste arquivo antes de encerrar a sessão.**

A memória do agente (arquivo externo de memória) é auxiliar e pode não existir na próxima sessão. Este `CLAUDE.md` é a única fonte de verdade persistente e confiável. Se a informação não está aqui, ela não existe para o próximo agente.

Fluxo obrigatório ao finalizar qualquer mudança:
1. Corrigir/implementar o código
2. Commitar
3. Atualizar este `CLAUDE.md` com o que mudou (seção "Histórico de sessões" e tabela de diagnóstico quando aplicável)
4. Só então encerrar

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
bibliotecas `.aq` do AltoQi Builder. Produz dois artefatos:

1. **Preview HTML standalone** (`output/preview/`) — visualização local ou via Vercel
2. **ZIP para bilds.com** (`output/<origem>/<slug>-AAAAMMDDHHMM.zip`) — upload no dashboard

O projeto é independente do `bilds-code-vercel` (apps/lps, vagas, seo).
Clonado em qualquer máquina, produz o mesmo resultado dado os mesmos inputs.

### A decisão central: a geometria vem do .aq, não do IFC

**O `.aq` carrega a malha 3D completa, com cor e miniatura.** Está no BLOB
`SIMBOLOGIA_3D.SIMBOLOGIA_3D`, no formato binário proprietário **OQ3D** — o mesmo
sólido que o AltoQi exporta como IFC. Os IFCs deixaram de ser necessários.

Validado em três bibliotecas de domínios e schemas distintos; ver
"Sessão 2026-08-24 — estudo OQ3D" no histórico. Ganhos:

- **85× a 421× mais rápido** que parsear os IFCs equivalentes
- **um arquivo de entrada** em vez de um `.aq` mais uma árvore de IFCs
- **zero matching por nome** — o vínculo peça → geometria é chave estrangeira
- os cinco bugs de parsing STEP documentados abaixo deixam de existir

---

## Fluxo do usuário

```
1. Clonar este repo
2. bash scripts/setup_vendor.sh   (baixa Three.js para templates/vendor/)
3. pip install -r requirements.txt
4. Copiar as bibliotecas .aq para input/, organizadas por fabricante:
       input/Dancor/pecas_dancor_bombas.aq
       input/Amanco/PVC Esgoto SN, SR e Silentium/pecas_amanco.aq
5. python3 scripts/build.py --all      ← um ZIP por .aq, sem perguntas
   (ou: python3 scripts/build.py       ← uma biblioteca, com perguntas)
6. Preview local: python3 -m http.server 8080 --directory output/preview
7. Subir output/<origem>/<slug>-AAAAMMDDHHMM.zip no dashboard.bilds.com → BIM 3D
```

### Os dois modos

| Modo | Comando | Geometria vem de |
|---|---|---|
| **Padrão** | `build.py` / `build.py --all` | do próprio `.aq` (OQ3D) |
| **Compatibilidade** | `build.py --ifc` | dos arquivos `.IFC` da pasta |

**Quando usar `--ifc`** — só nestes dois casos:

1. **Há peças em IFC ausentes do banco.** Caso real: a bomba 89-62 TJM da Dancor
   tem `.IFC` na pasta mas não existe no `.aq`, nem como `PECA`. Sem `--ifc` ela
   fica de fora. É o mesmo cenário que o `products_override` cobre.
2. **Conferir uma fonte contra a outra**, ao validar uma biblioteca nova.

Fora isso não use: é mais lento, exige `ifcopenshell` para IFCs B-rep e depende
do matching por nome, que erra em catálogos grandes (ver `find_aq_product`).
Com `--ifc`, os IFCs precisam estar **na mesma pasta do `.aq`** correspondente.

### Modo lote (`--all`)

Varre `input/` recursivamente, gera um catálogo por `.aq` e **espelha a estrutura
de pastas na saída**:

```
input/Amanco/linha/pecas.aq  →  output/Amanco/linha/<slug>-<ts>.zip
input/Dancor/pecas.aq        →  output/Dancor/<slug>-<ts>.zip
```

Bibliotecas que já têm ZIP no destino são **puladas**; `--force` refaz. Nada é
perguntado — fabricante, título e layout saem da inferência. Uma falha não
interrompe o lote: é registrada e o build segue para a próxima.

### O que é inferido automaticamente

| Campo | Fonte | Pergunta? |
|---|---|---|
| Fabricante | Prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` (`"AMANCO - PVC Esgoto SN"`) → pasta avô → pasta pai → 1º token do filename | Sim (não no `--all`) |
| Título | Pasta pai, se diferente do fabricante → tokens do filename → prefixo comum das linhas | Sim (não no `--all`) |
| Slug | `slugify(titulo)` — automático | Não, só exibido |
| Descrição | Nenhuma fonte automática | Sim, opcional |
| Layout | `series-rows` com curvas Q-H; `catalog-grid` acima de 6 peças | Sim (não no `--all`) |
| Geometria | `PECA_SIMBOLOGIA_3D` — chave estrangeira | Nunca |

> **Fabricante e título jamais podem sair vazios ou em forma de slug** — são o
> cabeçalho da página publicada. A cascata acima sempre produz algo legível.
> `PECA.BIBLIOTECA`, que era a fonte primária antiga, está **vazia nas três
> bibliotecas testadas**: não confie nela.

Quando o `.aq` detectado difere do `aq_file` do `config.json` (`aq_stale`),
fabricante, título e file_map são resetados — nunca herdam do catálogo anterior.

---

## Estrutura do projeto

```
bilds-bim-3d/
├── CLAUDE.md                    ← você está aqui
├── README.md                    ← guia para o usuário final
├── config.example.json          ← template de configuração
├── config.json                  ← criado pelo build, gitignored
├── requirements.txt             ← Jinja2 + numpy (ifcopenshell só p/ --ifc)
├── vercel.json                  ← serve output/preview/ como site estático
├── scripts/
│   ├── build.py                 ← pipeline principal (entry point)
│   ├── oq3d.py                  ← OQ3D binário → malha 3D  ★ caminho padrão
│   ├── read_aq.py               ← .aq AltoQi → dados, metadados e simbologias
│   ├── parse_ifc.py             ← IFC4 → JSON de geometria (só no modo --ifc)
│   ├── dedup.py                 ← deduplicação de vértices (~79% redução)
│   └── setup_vendor.sh          ← baixa Three.js para templates/vendor/
├── templates/
│   ├── layouts/
│   │   ├── series-rows.html     ← rows estilo Netflix por série (bombas)
│   │   └── catalog-grid.html    ← grid denso com filtros (conexões)
│   └── vendor/                  ← Three.js self-hosted (gitignored após setup)
├── input/                       ← bibliotecas do usuário — gitignored
│   └── <Fabricante>/[<Linha>/]<pecas>.aq
└── output/                      ← gerado pelo build
    ├── <origem>/<slug>-<ts>.zip        ← ZIP para bilds.com (gitignored)
    ├── <origem>/<slug>-catalog.json    ← catálogo solto (gitignored)
    ├── geo/<origem>/<slug>/*.json      ← geometria por produto (gitignored)
    └── preview/                        ← site estático, COMMITADO
        ├── index.html                  ← landing com a lista de catálogos
        ├── catalogs.json               ← índice dos catálogos gerados
        ├── vendor/                     ← Three.js
        └── <slug>/
            ├── index.html
            ├── catalog.json
            └── data/*.json             ← geometria servida ao viewer
```

> **`output/` espelha a estrutura de `input/`.** Os padrões do `.gitignore`
> precisam de `**` (`output/**/*.zip`), porque a saída é aninhada — `output/*.zip`
> só pegaria a raiz.

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

O arquivo é gerado em `output/<slug>-AAAAMMDDHHMM.zip` (ex: `dancor-bombas-incendio-202608241530.zip`).

```
<slug>-AAAAMMDDHHMM.zip
├── manifest.json    { slug, title, manufacturer, description, layout, filters, productCount }
├── catalog.json     dados completos dos produtos (campos em português)
└── geo/
    ├── cam-w10.json
    └── cam-w14.json
    ...
```

O dashboard.bilds.com lê `manifest.json` para exibir o nome/slug antes de processar
o zip inteiro. `catalog.json` e `geo/*.json` vão para S3, registrados no MongoDB.

> **Atenção:** `manifest.json` usa campos em **inglês** (contrato da API bilds.com).
> `catalog.json` usa campos em **português** (convenção de dados apresentados ao usuário).

---

## Conhecimento crítico: oq3d.py — a geometria dentro do .aq

Formato **OQ3D** (`OQ3D 3D Objects File`), no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`.
Árvore de objetos serializada no estilo Delphi:

```
0x5B <len:u32> <ClassName>   abre um objeto
...payload...
0x5D                         fecha
```

### Classes que carregam dados

```
TQi3DIndexedTriangleMeshData
    u32 versao(=2) | u32 nCoords | u32 reservado
    nCoords doubles                 → nCoords/3 vértices (x,y,z)
    u32 nIdx | u32 reservado
    nIdx u32                        → nIdx/3 triângulos
TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A    (cor UNIFORME da malha)
TCoordinateTransformation3D
    u32 versao | 12 doubles         → rotação 3×3 row-major + translação
```

Hierarquia: `TQi3DReusedObject(guid)` → `TQi3DReusableObject` (definição inline,
opcional) → `TQi3DTriangleMesh` → `TCoatingColor` + malha. O **último**
`TCoordinateTransformation3D` filho direto é o que posiciona; o par origem/alvo
espelha `MappingOrigin`/`MappingTarget` do IFC.

### Correspondência com o IFC

| OQ3D | IFC4 |
|---|---|
| `TQi3DObjectGroup` | `IFCELEMENTASSEMBLY` |
| `TQi3DReusableObject` | `IFCREPRESENTATIONMAP` |
| `TQi3DReusedObject` | `IFCMAPPEDITEM` |
| `TQi3DIndexedTriangleMeshData` | `IFCTRIANGULATEDFACESET` |
| `TCoordinateTransformation3D` | `IFCLOCALPLACEMENT` |
| `TCoatingColor` | `IFCINDEXEDCOLOURMAP` |

A contagem de entidades bate exatamente (18 `TQi3DReusedObject` ↔ 18
`IFCMAPPEDITEM`): o exportador IFC é tradução direta desta estrutura.

### Unidades

**Centímetros, Z-up** — a mesma orientação do IFC nativo.
Para Three.js: `x, y=z, z=-y`, multiplicado por 0.01.

### Armadilhas

| Armadilha | Consequência |
|---|---|
| Ignorar os transforms | Funciona em equipamentos (malhas já em coordenadas de mundo) e **quebra** em conexões, montadas de malhas reaproveitadas — joelhos saem retos. Use sempre o parser de árvore. |
| Buscar `0x5B` junto do byte anterior | O byte que precede varia (`\x02\x5b`, `\x01\x09\x00\x00\x00\x5b`…). Ancore só no `0x5B`. |
| Varrer delimitadores byte a byte | `0x5B`/`0x5D` ocorrem dentro de doubles. Consuma por inteiro os blocos de tamanho conhecido antes de varrer. |
| Somar bocais na bounding box | Verde `(1,154,63)` e azul `(10,84,152)` são marcadores de conexão, não produto — inflam a bbox em ~2 cm. Use `skip_markers=True`. |
| `SELECT *` em `SIMBOLOGIA_3D` | Traz o `WIREFRAME`: 69–71% do arquivo (285 MB dos 412 MB da Amanco), inútil para viewer web. |
| Esquecer o `dedup()` | O caminho `.aq` **precisa** dedupar como o IFC faz. Sem isso o preview foi de 148 MB para 571 MB. |

### API

```python
import oq3d
oq3d.is_oq3d(blob)                     # valida assinatura
oq3d.parse(blob)                       # árvore de nós
oq3d.extract(blob, skip_markers=True)  # [(verts_cm, tris, rgba)] com transforms
oq3d.to_buffers(blob)                  # {'pos','col','idx'} em metros, Y-up
oq3d.bbox(blob) / oq3d.stats(blob)     # validação e logs
```

### BUG ABERTO — instâncias repetidas não emitem geometria

`TQi3DReusedObject` **sem** definição inline referencia a malha por GUID, mas os
GUIDs são **únicos por instância** — a chave de resolução não foi identificada.

Na CAM-W21 2CV: **5 instâncias com malha própria, 13 só com transform**, que não
emitem nada. Efeito visível: parafusos faltando, e um deles aparece solto no ar
(a definição inline é desenhada na posição da sua própria instância, longe do
corpo). Confirmado em produção no preview da Dancor.

Não afeta a silhueta do produto — os renders continuam equivalentes ao IFC —
mas é a próxima coisa a resolver. Hipóteses a testar: o `u32` em `+8` do payload
do `TQi3DReusedObject` (valores observados: 1..6) pode ser índice da definição;
ou a definição a herdar é a última vista no mesmo nível da árvore.

---

## Conhecimento crítico: parse_ifc.py (modo `--ifc`)

> Só usado com `--ifc`. No caminho padrão nada disto é executado — e os cinco
> bugs abaixo, todos de parsing de texto STEP, deixam de existir.

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

## Conhecimento crítico: build.py — matching IFC → .aq

### find_aq_product — como o match funciona

```python
find_aq_product(slug, product_map, ifc_path_hint=None)
```

Quando o `file_map` usa caminhos relativos como chave (ex: `"Cap/PVC Esgoto SN/100mm.ifc"`),
o `ifc_path_hint` é passado automaticamente por `build_catalog()`. O algoritmo extrai tokens
de **todos** os componentes do caminho (pasta + filename) e calcula cobertura contra o GRUPO_PECA:

```
caminho: "Cap/PVC Esgoto SN/100mm.ifc"
tokens query: {cap, pvc, esgoto, sn, 100mm}

GRUPO_PECA "Cap" → tokens {cap} → cobertura 1/1 = 100% ✓
→ dentro do grupo: PECA com maior sobreposição com leaf "100mm"
→ nome final: "Cap 100mm" (gp + peca quando grupo não está no nome da peça)
```

Tenta cobertura ≥ 100%, relaxa para ≥ 75% se não encontrar. Se ainda falhar,
cai no fallback por prefixo/número (compatível com IFCs flat como Dancor).

**Para maximizar o match rate em catálogos hierárquicos:** a chave do `file_map`
deve ser o caminho relativo completo a partir do `ifc_dir`, não só o filename.
Para catálogos com > 50 produtos, o `interactive_config()` gera isso automaticamente
via modo `'recursive'` do `scan_input()`.

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
| Taxa de match IFC → .aq baixa | `file_map` usa só filename — chave deve ser o caminho relativo completo (`Cap/PVC SN/100mm.ifc`) para enriquecer tokens da busca fuzzy |
| Nome do produto é só dimensão ("100mm") | Esperado para catálogos flat no .aq — build.py prefixa com GRUPO_PECA automaticamente |
| ZIP 0KB + "X não encontrado em input/" | scan_input escolheu modo subdir com múltiplos IFCs — fix: modo subdir só ativa quando cada subdir tem exatamente 1 IFC; caso contrário cai em recursive |
| Fabricante/título stale do catálogo anterior | aq_stale não estava resetando titulo/slug — fix em commit 056e729; deletar config.json corrompido se necessário |
| `Fabricante []` sem sugestão | BIBLIOTECA vazia no .aq e pasta avô é genérica — peek_aq tenta pasta avô, depois filename |
| Título sugerido ruim (ex: `"Esgoto Sn Sr"`) | Pasta pai do .aq é genérica (`input/`, `.`) — organizar como `input/Fabricante/Nome da Linha/pecas.aq` |
| Slug com acento (`inc-ndio`) | slugify não normalizava unicode — corrigido com NFD + strip combining marks (commit 8e2f67d) |
| Slug mostra valor antigo do config.json | ec.get('slug') tomava precedência sobre titulo atual — removido; slug sempre = slugify(titulo) (commit fefb627) |
| **Fabricante vazio na página publicada** | `PECA.BIBLIOTECA` está vazia nas três bibliotecas testadas — usar o prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` |
| **Título vira o nome do fabricante** | Pasta pai é o fabricante (`input/Intelbras/pecas_Intelbras_*.aq`) — comparar o slug da pasta com o 1º token do arquivo antes de usá-la como título |
| **Título em forma de slug** na página | Derivado do filename sem limpeza — remover ruído (`pecas`, anos, versões), preservar siglas (CFTV, PPCI) e separar CamelCase |
| Nome do produto redundante (`Pontos de comando Interruptor…`) | Prefixo do grupo aplicado sem necessidade — prefixar só quando o nome é ambíguo, decidindo **por grupo** |
| **Preview 404 em `data/*.json`, erro `Unexpected token 'T'`** | Template usava `./data/`; com `cleanUrls` a página é servida em `/<slug>` sem barra final e o relativo vai para a raiz. Usar caminho absoluto `'/' + CATALOG.slug + '/data/'`. O `'T'` é a página 404 da Vercel ("The page…") caindo no `JSON.parse` |
| Preview gigante (centenas de MB) | Faltou `dedup()` no caminho `.aq` — reduz ~79% dos vértices |
| ZIPs entrando no commit | `output/*.zip` não cobre subpastas; a saída é aninhada — usar `output/**/*.zip` |
| Joelhos e curvas retos no viewer | Transforms do OQ3D ignorados — usar o parser de árvore de `oq3d.py` |
| Peças 100× maiores/menores | OQ3D é **centímetros**; multiplicar por 0.01 |
| Menos produtos que peças no banco | Peças sem `PECA_SIMBOLOGIA_3D` são tubos e kits — sem forma fixa, pular é o correto |
| Parafusos faltando / um solto no ar | Bug aberto do OQ3D — ver "instâncias repetidas não emitem geometria" |

---

## Git e deploy

**Identidade:** commits neste repo usam `carlosnetoaltoqi`.
Verificar com `git config user.name` e `git config user.email`.
Se necessário: `git config user.name "carlosnetoaltoqi"`

**output/preview/** NÃO é gitignored (é o artefato de preview commitado).
Inclui `output/preview/data/` — geo JSONs servidos pelo preview (commitados junto).
**output/geo/** e **output/*.json** SÃO gitignored (cópias locais de trabalho).

### Deploy na Vercel

**Projeto:** `bilds/bilds-bim-3d` — **não criar outro projeto, nunca.**
**URL de produção:** https://bilds-bim-3d.vercel.app

O repositório está conectado à Vercel via integração git — **o push para `main` dispara o
deploy automaticamente**. Fluxo normal:

```bash
git add output/preview/
git commit -m "build: catálogo {slug}"
git push
```

O `vercel.json` na raiz configura `"outputDirectory": "output/preview"` — a Vercel serve
esse diretório. Para deploy manual via CLI (ex: sem commit):

```bash
# SEMPRE da RAIZ do repo
vercel --prod --yes
```

**Nunca** passar `output/preview` como argumento posicional (`vercel deploy output/preview --prod`)
— isso ignora o `.vercel/project.json` da raiz e cria um projeto novo indesejado.

**Preview local:**
```bash
python3 -m http.server 8080 --directory output/preview
```

---

## Histórico de sessões

### 2026-08-23 — Diagnóstico e correção de bugs do parse_ifc.py

**Contexto:** primeira vez que o pipeline foi rodado do zero após limpeza total do `output/`.
Os arquivos de geo que existiam localmente (gitignored) nunca tinham sido regenerados desde
a criação do projeto — esta sessão revelou que o código commitado nunca havia sido validado
contra os IFCs reais.

**Bug 1 — Índices errados no parser STEP (Dancor / CATIA / 3DEXPERIENCE)**

`parse_ifc.py` lia `parts[4]` como `ObjectPlacement` e `parts[5]` como `Representation`.
No IFC4 exportado pelo 3DEXPERIENCE, o índice 4 (0-based) é `ObjectType`
(`'AECARCHITECTURALELEMENT'`), deslocando tudo em +1:

```
[4] ObjectType       = 'AECARCHITECTURALELEMENT'  ← o que estava sendo lido como LP
[5] ObjectPlacement  = #id do IFCLOCALPLACEMENT   ← correto
[6] Representation   = #id do IFCPRODUCTDEFINITIONSHAPE
```

O parser tentava `int('AECARCHITECTURALELEMENT')` → `ValueError` → pulava todos os
`IFCBUILDINGELEMENTPROXY` → 0 vértices para todos os 14 IFCs da Dancor.

**Correção aplicada:** `parts[4]→parts[5]` (ObjectPlacement) e `parts[5]→parts[6]`
(Representation). Guard `len(parts) < 7` atualizado de `< 6`.

**Bug 2 — IFCs da Amanco usam IFCADVANCEDBREP, não IFCTRIANGULATEDFACESET**

O `parse_ifc.py` só tratava geometria tessellada (`IFCTRIANGULATEDFACESET`).
Os IFCs da Amanco (exportados pelo AltoQi Hidráulico/Elétrico) usam B-rep paramétrico
(`IFCADVANCEDBREP`) — incompatível com o parser STEP puro.
Os geo files da Amanco em commits anteriores foram gerados em sessão com código diferente.

**Correção aplicada:** adicionado `_parse_ifc_brep()` que usa `ifcopenshell.geom`
para tessellizar B-rep automaticamente, com fallback de cor por material.
`parse_ifc_file()` detecta o tipo de geometria e roteia para o método correto.
`ifcopenshell>=0.8.0` adicionado ao `requirements.txt`.

**Bug 3 — `build_entity_index` capturava `) ;` como parte dos args**

A regex primária de `build_entity_index` usava `(.*)(?:\)\s*;?)?` onde o grupo opcional
nunca fazia backtrack — o `(.*)` greedy consumia o `) ;` final da linha.
Resultado: args de `IFCLOCALPLACEMENT(#27,#46) ;` eram indexados como `'#27,#46) ;'`.

Ao chamar `resolve_lp` → `split_top('#27,#46) ;')` → `['#27', '#46) ;']` →
`int('#46) ;'.lstrip('#'))` → `int('46) ;')` → `ValueError` → todas as entidades puladas.

**Correção aplicada:** substituição da regex bugada pela regex de fallback (que já estava
correta, usando `(.*)\)\s*;?\s*$` com backtracking forçado até o último `)` da linha):
```python
# Antes (bugado):
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)(?:\)\s*;?)?\s*$', line)
if not m:
    m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line, re.DOTALL)

# Depois (correto — uma única regex):
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line)
```

**Bug 4 — `_process_faceset` lia CoordIndex do campo errado**

`IFCTRIANGULATEDFACESET` tem 5 atributos: `Coordinates, Normals, Closed, CoordIndex, PnIndex`.
O código lia `fs_parts[1]` (Normals) como CoordIndex em vez de `fs_parts[3]`.
Nos arquivos Dancor/CATIA, `Normals` contém vetores float (`((0.3,0.9,...),...)`) —
`parse_ints` extraía dígitos desses floats como "índices", gerando `IndexError` ao
acessar `coord_list[vi-1]`.

**Correção aplicada:** `coord_index_str = fs_parts[1]` → `fs_parts[3]`.
Guard atualizado de `len(fs_parts) < 2` → `< 4`.

**Estado pós-correção e validação:**
- Dancor: todos os 14 IFCs parseados com 50k–150k vértices cada; redução ~79% pelo dedup
- Pipeline completo rodou com sucesso: parse → dedup → catalog.json → preview HTML → ZIP
- Amanco: código de B-rep implementado (ifcopenshell), mas estrutura de dirs aninhada ainda
  limita quais categorias são detectadas pelo `scan_input` (problema arquitetural separado)

### 2026-08-24 — Bug 5: parse_floats quebrava em notação científica sem dígito fracionário (commit 2bf5607)

Coordenadas IFC exportadas pelo CATIA usam formato `-4.E-16` e `1.E+00` — notação científica
sem dígitos entre o ponto decimal e o expoente. A regex `[0-9]*\.?[0-9]+` exigia ao menos
um dígito após o ponto, então `-4.E-16` era extraído como dois números: `-4` e `-16`.

Resultado: sub-peças com esse valor de coordenada (INTERMEDIARIA, MOTOR) apareciam
deslocadas exatamente em 16m do corpo da bomba.

Bombas afetadas: 105-50 TJM, 51-30W TJM, 109_40 TJM.

```python
# Regex corrigida — aceita ponto sem dígito fracionário
r'[-+]?(?:[0-9]+\.?[0-9]*|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
```

### 2026-08-24 — Correções de documentação e pipeline

- `build_zip()` em `build.py`: manifest.json gerado com campos em **inglês** conforme
  contrato da API bilds.com (`title`, `manufacturer`, `description`, `filters`, `productCount`).
  Antes usava os mesmos campos em português do `catalog.json`.
- ZIP renomeado de `bilds-upload.zip` para `<slug>-AAAAMMDDHHMM.zip`.
- `output/preview/.gitignore` criado para excluir `*_raw.json` (artefatos do CLI do parse_ifc).
- Skill `leitor-ifc` atualizada para v1.3.0 com todos os 5 bugs e suas correções documentadas.

### 2026-08-24 — Matching fuzzy IFC → .aq por cobertura de tokens (commit d75cf7b)

`find_aq_product(slug, product_map, ifc_path_hint=None)` — substituição do match por
prefixo simples por scoring de cobertura de tokens:

- **Tokenização do caminho**: todos os componentes do path relativo do IFC viram tokens
  (ex: `"Cap/PVC Esgoto SN/100mm.ifc"` → `{cap, pvc, esgoto, sn, 100mm}`).
- **Score de grupo**: `covered_tokens / total_gp_tokens`. Exige ≥ 100%; relaxa para ≥ 75%
  se não encontrar nada. Em empate, prefere o grupo com mais tokens (mais específico).
- **Score de peça**: dentro do grupo vencedor, a PECA com maior sobreposição com o leaf
  (nome do arquivo sem extensão e sem pasta) é selecionada.
- **Nome composto**: se o nome do GRUPO_PECA não está contido no nome da PECA, o build
  produz `f"{nome_gp} {peca['nome']}"` como nome do produto (ex: `"Cap 100mm"`).
- **Fallback**: prefixo/número preservado para IFCs flat sem hierarquia (Dancor).

`build_catalog()` passa `ifc_name` (a chave do `file_map`) como `ifc_path_hint`.

### 2026-08-24 — interactive_config: aq_stale, scan_input e inferência do .aq (commits 572956a…8c2deff)

**Bug 7 — scan_input modo subdir com múltiplos IFCs quebrava o parse (commit fb7dcc8)**

`input/Dancor/` com 14 IFCs era detectado como modo `subdir` (1 produto = subdir inteiro).
O display name `"Dancor/ (14 IFCs)"` ia como chave do `file_map`; o parser tentava abrir
esse string como arquivo → AVISO + ZIP 0KB.

Correção: modo `subdir` só ativo quando cada subdir tem **exatamente 1 IFC**; caso contrário
cai em modo `recursive` (cada IFC = um produto).

**Bug 8 — aq_stale não resetava titulo/slug (commit 056e729)**

Quando o .aq mudava (ex: Amanco → Dancor), `fabricante` era resetado mas `titulo` e `slug`
continuavam vindo do `config.json` stale. Slugs errados (ex: `"amanco-conexoes"`) persistiam
para o novo catálogo.

Correção: quando `aq_stale=True`, `sug_titulo` e `sug_slug` derivam apenas dos hints/filename
do novo .aq, não do `ec` (config existente).

**Bug 9 — fabricante e título não inferidos do filename do .aq (commit 8c2deff)**

Campo `BIBLIOTECA` na Dancor .aq está vazio → `hints['fabricante'] = ''` → prompt sem default.

Correção: `peek_aq()` analisa o filename após falha no banco:
- `pecas_dancor_bombas_incendio_2026_04.1.aq` → remove ruído (`pecas`, anos `2026`, versão `04`)
- 1º token restante = fabricante (`Dancor`)
- Tokens restantes = título (`Bombas Incendio`)

Resultado: usuário passa por `--interactive` só com Enter em todos os campos.

**Bug 10 — slugify não normalizava acentos (commit 8e2f67d)**

`re.sub(r'[^a-z0-9]+', '-', s.lower())` convertia `ê` em `-` (não é ASCII).
`"Incêndio"` → `"inc-ndio"`. Corrigido com NFD + strip combining marks:
```python
s = unicodedata.normalize('NFD', s)
s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
```
Agora: `"Bombas de Combate a Incêndio"` → `"bombas-de-combate-a-incendio"`.

**Bug 11 — slug derivava de fabricante+1ªpalavra, não do título completo (commits 8e2f67d, fefb627)**

`sug_slug` usava `f"{fabricante}-{titulo.split()[0]}"` → `"dancor-bombas"` em vez de
`"bombas-de-combate-a-incendio"`. Além disso, `ec.get('slug')` tomava precedência e
exibia o slug antigo do `config.json` mesmo após o usuário alterar o título.

Correção: `sug_slug = slugify(titulo or fabricante or 'catalogo')` — sempre re-calculado
a partir do título confirmado na pergunta anterior, sem herdar valor do config.

### 2026-08-24 — Refinamentos do modo interativo (sessão 2, commit c740086 → 5f2f2d2)

**Slug removido do fluxo interativo**

A pergunta `Slug da URL [...]` foi removida — o slug é calculado automaticamente de
`slugify(titulo)` e apenas exibido. O usuário não precisa confirmar nem editar.

Motivação: slug é derivado do título; pedir os dois é redundante. Para alterar o slug
basta alterar o título.

**peek_aq usa hierarquia de pastas como fonte primária de título e fabricante**

Antes, `peek_aq` usava o campo `BIBLIOTECA` do banco e o filename do `.aq` como fallback,
produzindo títulos de baixa qualidade (ex: `"Esgoto Sn Sr Silentium"` do filename).

Correção: lê `parent_dir` (pasta pai do `.aq`) como título e `grandpa_dir` (avô) como
fabricante, antes de qualquer fallback por filename. Pasta pai é o nome real da linha de produto.

```
input/Amanco/PVC Esgoto SN, SR e Silentium/pecas.aq
              ↑ grandpa → fabricante        ↑ parent → título
```

Resultado: título sugerido passa a ser `"PVC Esgoto SN, SR e Silentium"` (correto) em vez de
`"Esgoto Sn Sr Silentium"` (ruim). Diretórios genéricos (`input`, `bim`, `.`) são ignorados.

**Regra de commits estabelecida**

Mensagens de commit devem descrever features e decisões, nunca associar a fabricantes ou
dados de input (fabricantes são variáveis e efêmeros).
- Correto: `feat(peek_aq): inferir título da pasta pai do .aq`
- Errado: `feat: pipeline validado com Amanco 502 IFCs`

**Ponto estável: commit `6336f60`** — pipeline completo, documentação autocontida, preview dos dois catálogos no repo.
Para retornar: `git checkout 6336f60`.

### 2026-08-24 — Bug WebGL: shared renderer + JPEG capture (commits b73ee8a, 35d63db)

**Problema:** ao rolar para baixo e carregar muitos cards 3D, depois voltar para cima,
as miniaturas desapareciam. Console exibia: `WARNING: Too many active WebGL contexts. Oldest context will be lost.`

O código anterior criava um `WebGLRenderer` por card via `IntersectionObserver` e nunca
destruía o contexto — o browser limita a ~8–16 contextos simultâneos.

**Arquitetura nova: shared renderer + JPEG capture**

- `sharedRenderer`: um único `WebGLRenderer` com `preserveDrawingBuffer: true`, criado
  sob demanda e reutilizado sequencialmente para todos os thumbnails.
- Após render: `canvas.toDataURL('image/jpeg', 0.88)` → `<img>` tag. Zero contextos WebGL
  persistentes por card.
- `thumbCache (Map<id, dataURL>)`: sobrevive a filtros (DOM é destruído/recriado ao filtrar).
  Quando card volta ao DOM, restaura do cache sem re-render.
- `renderQueue + processQueue`: fila sequencial garante um render por vez.
- `activeCard`: viewer interativo ao clicar no thumb (OrbitControls + loop de animação).
  `IntersectionObserver` deativa automaticamente ao sair da viewport e restaura o thumb.
- `disposeScene`: libera geometrias e materiais da GPU após cada thumbnail.
- Máximo 3 contextos WebGL em qualquer momento: `sharedRenderer` + `activeCard.renderer`
  + `modalViewer.renderer`.

**Bug 12 — `observeCards()` não chamado no carregamento inicial (commit 35d63db)**

O evento `cards-rendered` disparava no script síncrono (durante o parse do HTML), mas
o listener no módulo ES só registrava após `DOMContentLoaded` — chegava tarde demais.
Resultado: Amanco não carregava miniaturas até o primeiro clique em filtro.

Correção: adicionar `observeCards()` direto após o `addEventListener` no módulo, além
de manter o listener para re-renders (ao filtrar).

**Ponto estável: commit `35d63db`** — WebGL context overflow resolvido, validado em produção.
Para retornar: `git checkout 35d63db`.

### 2026-08-24 — Estudo OQ3D: a geometria sai do .aq (commits 912bf38, 8414bb2, 9b85f6c)

**A descoberta.** O `.aq` não é só o banco de dados de produto: carrega a malha 3D
completa, com cor e miniatura, no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`, em formato
binário proprietário (OQ3D). É o mesmo sólido que o AltoQi exporta como IFC.
Consequência: **os IFCs deixaram de ser necessários** no caminho padrão.

**Como foi validado.** Três bibliotecas de naturezas opostas, mais um teste cego:

| Biblioteca | Schema | Peças | Geometrias | IFCs de contraprova |
|---|---|---|---|---|
| Dancor (bombas) | 607 | 13 | 13 | 14, tessellated |
| Amanco (conexões PVC) | 595 | 1.168 | 457 | 502, `IFCADVANCEDBREP` |
| Intelbras (elétrica) | 572 | 32 | 18 | nenhum — teste cego |

Onde o IFC é tessellated, os triângulos batem **exatamente** (37-40 TJM: 44.951 em
ambos). Onde é B-rep, a forma converge a 0,3 mm mas a tesselação é independente —
o IFC guarda o sólido exato e é retessellizado a cada leitura, o `.aq` traz a malha
que o AltoQi fixou. O lote final rodou sobre **9 bibliotecas e seis versões de
schema** (552, 562, 572, 582, 595, 607) sem uma falha.

**Bug do parser linear (achado na Amanco).** Nas bombas, as malhas já vêm em
coordenadas de mundo — dá para ignorar os transforms e ainda renderizar certo. Nas
conexões **não**: cada peça é montada de malhas reaproveitadas e posicionadas por
`TCoordinateTransformation3D`. O primeiro parser produzia joelhos retos. Exigiu
parser de árvore com pilha (`scripts/oq3d.py`).

**Bug colateral no `parse_ifc.py` — ainda aberto.** Ao resolver o Caminho B, o
código procura o face set direto dentro do `IFCREPRESENTATIONMAP`, mas falta um
nível: `IFCMAPPEDITEM → IFCREPRESENTATIONMAP → IFCSHAPEREPRESENTATION →
IFCTRIANGULATEDFACESET`. Na CAM-W21 isso descarta 3.231 triângulos (13,8%) — as
peças instanciadas. Afeta só o modo `--ifc`.

**O `file_map` morreu.** O vínculo `PECA → PECA_SIMBOLOGIA_3D → SIMBOLOGIA_3D` é
chave estrangeira. O matching por tokens do `find_aq_product` é comprovadamente
frágil: ao tentar parear os 502 caminhos de IFC da Amanco com os nomes do banco,
`Junção Simples + Joelho 45/Com luva` casou com `Luva Simples 200MM` — cobertura
100%, peça errada.

**Variantes com e sem luva.** O AltoQi exporta **dois IFCs por peça** (com e sem a
luva de encaixe) e o banco guarda só a canônica — a com luva. Explica os 502 IFCs
para 457 geometrias. Medindo por bounding box: 76% de cobertura nos "com luva",
1,5% nos "sem luva".

**Peças sem forma fixa.** 312 das 1.168 peças da Amanco (27%) não têm geometria, e
é o correto: tubos (cilindro paramétrico por diâmetro × comprimento) e kits de
aparelho sanitário. O build informa quantas pulou.

**Erros cometidos nesta sessão, e o que ensinaram:**

- **Faltou o `dedup()`** no caminho `.aq` — só o caminho IFC aplicava. O preview
  foi para 571 MB; com dedup, 347 MB para 9 catálogos (antes: 155 MB para 2).
- **`output/*.zip` não cobre subpastas.** Como a saída passou a espelhar o input,
  os 9 ZIPs escaparam do gitignore. Corrigido com `output/**/*.zip`.
- **`./data/` quebra com `cleanUrls`.** Mover o `data/` para dentro do catálogo
  (necessário: `50mm.json` colide entre bibliotecas) expôs que a página é servida
  em `/<slug>` sem barra final, e o relativo resolve para a raiz. O sintoma
  enganoso era `Unexpected token 'T'` — a página 404 da Vercel caindo no
  `JSON.parse`. Agora o `fetch` checa `r.ok` antes de parsear.

**Pendência conhecida:** parafusos faltando na Dancor — 13 de 18 instâncias não
emitem geometria, e uma definição aparece solta no ar. Ver "BUG ABERTO" na seção
do `oq3d.py`.

**Ponto estável: commit `9b85f6c`** — 9 catálogos em produção, geometria servindo
200 em todos. Para retornar: `git checkout 9b85f6c`.
