# CLAUDE.md — bilds-bim-3d

Ponto de entrada para qualquer agente ou humano que trabalhe neste projeto.

---

## OBRIGATÓRIO: ler as specs antes de qualquer ação

**Antes de rodar o pipeline, depurar um bug, editar qualquer arquivo ou responder
qualquer pergunta técnica sobre este projeto, leia as três specs abaixo.**

Elas documentam bugs confirmados em produção, schemas exatos de entidades IFC4,
armadilhas de parse e padrões de template validados. Ignorar as specs é a causa
mais comum de reintroduzir bugs que já foram corrigidos.

```
docs/specs/leitor-ifc.md            ← parse_ifc.py, dedup.py
docs/specs/leitor-biblioteca-aq.md  ← read_aq.py
docs/specs/pagina-biblioteca.md     ← templates/layouts/*.html, build.py
```

Mapeamento arquivo → spec obrigatória:

| Arquivo | Spec |
|---|---|
| `scripts/parse_ifc.py` | `docs/specs/leitor-ifc.md` |
| `scripts/dedup.py` | `docs/specs/leitor-ifc.md` |
| `scripts/read_aq.py` | `docs/specs/leitor-biblioteca-aq.md` |
| `scripts/build.py` | as três specs |
| `templates/layouts/*.html` | `docs/specs/pagina-biblioteca.md` |

Ao iniciar qualquer tarefa neste projeto, execute:
```
Read docs/specs/leitor-ifc.md
Read docs/specs/leitor-biblioteca-aq.md
Read docs/specs/pagina-biblioteca.md
```

---

## Protocolo de sessão — "vamos trabalhar no bilds-bim-3d"

Quando o operador iniciar uma sessão com o prompt **"vamos trabalhar no bilds-bim-3d"**
(ou variações próximas como "rodar bilds-bim-3d", "continuar o bilds-bim-3d"), aplicar
este protocolo de autonomia total sem pedir confirmação a cada passo:

### 1. Início de sessão — sempre

1. Ler as três specs em `docs/specs/` (ver seção OBRIGATÓRIO acima)
2. Verificar `git status` e `git log --oneline -5` para entender o estado atual
3. Perguntar ao operador o que será feito nesta sessão

### 2. Durante o trabalho — para cada mudança completa

Após qualquer decisão de mudança (edição de arquivo, geração de catálogo, correção de bug):

```bash
# 1. Rodar o build (--yes protege o file_map; --skip-ifc se geo já existe)
python3 scripts/build.py --yes [--skip-ifc]

# 2. Commit local
git add <arquivos relevantes>
git commit -m "<mensagem descritiva>"

# 3. Push remoto
git push

# 4. Deploy na Vercel (preview do projeto)
vercel deploy output/preview/ --prod
```

**Não esperar o operador pedir** — commit + push + deploy são parte do fluxo normal,
não ações especiais. O operador assumirá que isso aconteceu automaticamente.

### 3. Pull Request

Criar PR quando a mudança for uma feature ou correção com escopo definido:

```bash
gh pr create --title "<título curto>" --body "$(cat <<'EOF'
## O que mudou
- <bullet 1>

## Testado
- [ ] Preview local
- [ ] Deploy Vercel
EOF
)"
```

Não criar PR para: commits de docs/specs isolados, ajustes menores de configuração,
ou quando o operador estiver claramente em modo iterativo rápido (muitos commits
seguidos na mesma feature).

### 4. Vercel — configuração de deploy

O deploy usa `output/preview/` como diretório de saída:

```bash
vercel deploy output/preview/ --prod
```

Se o projeto Vercel não estiver linkado na máquina:
```bash
vercel link   # selecionar projeto bilds-bim-3d no team BILDS
vercel deploy output/preview/ --prod
```

O preview fica em `https://bilds-bim-3d.vercel.app` (ou domínio customizado se configurado).

### 5. Identidade git obrigatória

Verificar antes do primeiro commit:
```bash
git config user.name   # deve ser: carlosnetoaltoqi
git config user.email  # deve ser: 190008472+carlosnetoaltoqi@users.noreply.github.com
```

Se não estiver configurado:
```bash
git config user.name "carlosnetoaltoqi"
git config user.email "190008472+carlosnetoaltoqi@users.noreply.github.com"
```

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

**Primeira vez (sem config.json):**
```
1. Clonar este repo
2. bash scripts/setup_vendor.sh      ← baixa Three.js para output/preview/vendor/
3. pip install -r requirements.txt   ← instala Jinja2
4. Copiar arquivos .IFC e .aq para input/
5. python3 scripts/build.py          ← modo interativo: cria config.json + roda tudo
6. Preview: python3 -m http.server 8080 --directory output/preview
7. Abrir: http://localhost:8080/{slug}
8. Subir output/bilds-upload.zip no dashboard.bilds.com → BIM 3D
```

**Sessões seguintes (config.json já existe, IFCs já parseados):**
```
python3 scripts/build.py --yes --skip-ifc
```

**Sessões seguintes (re-parsear IFCs, ex: depois de limpar output/geo/):**
```
python3 scripts/build.py --yes
```

> **config.json é gitignored** — nunca commitado. Cada máquina cria o seu via modo
> interativo ou copiando manualmente. `output/geo/` também é gitignored — sempre
> gerado localmente pelo parse.

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

### Regra: sempre gerar os dois layouts no preview

**Todo build sempre gera os dois layouts para o preview**, independente do `"layout"` configurado no `config.json`. O `config.json` define o layout primário (`index.html`); os outros dois ficam como alternativas navegáveis.

Estrutura de saída obrigatória em `output/preview/{slug}/`:
```
index.html          ← layout primário (do config.json)
series-rows.html    ← sempre gerado
catalog-grid.html   ← sempre gerado
data/               ← geo JSONs (compartilhados pelos três HTMLs)
```

URLs no preview Vercel:
- `/{slug}/` → layout primário
- `/{slug}/series-rows` → view alternativa rows
- `/{slug}/catalog-grid` → view alternativa grid

**O ZIP para bilds.com NÃO é afetado** — ele contém apenas `manifest.json`, `catalog.json` e `geo/*.json`, sem HTMLs. O layout primário fica registrado no MongoDB via dashboard, não no ZIP.

Para adicionar um novo layout:
1. Criar `templates/layouts/meu-layout.html` usando os mesmos padrões (ver seção abaixo)
2. Usar `"layout": "meu-layout"` no config.json
3. Adicionar ao loop de geração dos layouts alternativos no `build.py`

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

**Fix de timing obrigatório:** o script sync dispara `cards-rendered` durante o parse da página, antes do módulo estar pronto para ouvir. Chamar `observeCards()` diretamente no final do módulo além de ouvir o evento:

```javascript
document.addEventListener('cards-rendered', () => observeCards());
document.addEventListener('modal-open', e => initModalViewer(e.detail.id));
observeCards(); // cards já estão no DOM quando o módulo carrega — OBRIGATÓRIO
```

Sem essa chamada direta, as miniaturas só carregam quando o usuário clica em algum filtro (re-renderiza os cards, dispara novo `cards-rendered`).

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

## Conhecimento crítico: build.py

### Modos de execução

`build.py` tem dois modos:

**Interativo** (padrão — sem `--yes`): exibe prompts para cada campo. Se `config.json`
existe, usa como defaults; o operador pressiona Enter para aceitar. **Atenção:** o modo
interativo chama `scan_input()` que detecta a estrutura de `input/`. Se `input/` tiver
subdirs (ex: `Amanco/`, `Dancor/`), vai sugerir slugs de diretório em vez dos slugs por
produto. Nesses casos, preferir `--yes` para proteger o `file_map` existente.

**Não-interativo** (`--yes` / `-y`): usa `config.json` como está, sem perguntas.
Requer `config.json` existente. É o modo seguro para sessões repetidas.

Flags úteis:
- `--yes` / `-y` — usa config.json sem modo interativo. **Usar sempre em sessões seguintes.**
- `--skip-ifc` — pula o `parse_ifc.py` e usa os JSONs de `output/geo/` já existentes.
  Combinar com `--yes` para rebuild rápido: `python3 scripts/build.py --yes --skip-ifc`

### slugify() — normalização unicode obrigatória

Caracteres portugueses (`ç`, `ã`, `é`, etc.) devem ser transliterados antes do regex.
Sem isso, `Junção` vira `jun-o` em vez de `juncao`:

```python
def slugify(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
```

### scan_input() — detecção de subdirs e 3-tuples

Em modo subdir (IFCs organizados em pastas por categoria), `scan_input()` usa
`os.walk` recursivo e retorna **3-tuples** `(ifc_path, slug, label)`.
Em modo flat, retorna **2-tuples** `(ifc_path, slug)`.

`interactive_config()` trata os dois casos:
```python
if len(entry) == 3:
    ifc_path, slug, label = entry
else:
    ifc_path, slug = entry
    label = slug
```

**Armadilha:** se as chaves do `file_map` no `config.json` existente não coincidirem
exatamente com o que `scan_input()` gera (mesmo slug gerado por `slugify(categoria)`),
o modo interativo não reconhece os defaults e sobrescreve o `file_map` com slugs
das categorias em vez dos slugs por produto. Solução: garantir que as chaves do
`file_map` no `config.json` sejam exatamente os paths relativos ao `ifc_dir` que
o `scan_input()` gera.

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

### Padrão de thumbnail estática + hover 3D

Não inicializar todos os viewers simultaneamente — GPU explode com 10+ contextos WebGL.
- `IntersectionObserver` com `rootMargin:'120px'` para lazy load
- `renderer.render()` uma vez → thumbnail estática
- OrbitControls + loop de animação ativado por **mouseenter**, parado por **mouseleave**

**Implementação canônica** (ver `catalog-grid.html`):

```javascript
thumbStates.set(id, {renderer, scene, camera, raf: null, controls: null, rotating: false});

canvas.addEventListener('mouseenter', () => {
  const st = thumbStates.get(id);
  if (!st) return;
  if (!st.controls) {
    if (badge) badge.classList.add('off');
    const controls = new OrbitControls(camera, canvas);
    controls.autoRotate = true; controls.autoRotateSpeed = 1.2;
    controls.enableDamping = true; controls.dampingFactor = 0.07;
    controls.enableZoom = false; controls.enablePan = false;
    st.controls = controls;
    st.spin = function() {
      if (!st.rotating) { st.raf = null; return; }
      st.raf = requestAnimationFrame(st.spin);
      controls.update(); renderer.render(scene, camera);
    };
  }
  st.rotating = true;
  if (!st.raf) st.spin();
});
canvas.addEventListener('mouseleave', () => {
  const st = thumbStates.get(id);
  if (!st) return;
  st.rotating = false;
  renderer.render(scene, camera); // freeze frame
});
```

`series-rows.html` já usa o padrão hover 3D (mesmo de `catalog-grid.html`).

### Cache de geometria

```javascript
const geoCache = new Map(); // filename → data
async function fetchGeo(geo) {
  if (geoCache.has(geo)) return geoCache.get(geo);
  const data = await fetch('/data/' + geo).then(r => r.json()); // path ABSOLUTO — pages vivem em /{slug}/
  geoCache.set(geo, data); return data;
}
```

**CRÍTICO:** usar `/data/` (absoluto), nunca `./data/`. A página fica em `/{slug}/`, então `./data/` resolve para `/{slug}/data/` — 404 garantido.

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

## Planos pendentes

Arquivos em `docs/`:

| Arquivo | O que faz |
|---|---|
| `plan-bim-catalog-hero-hover.md` | Porta hero section + hover 3D para os componentes React do bilds.com (`CatalogGridLayout.tsx`, `SeriesRowsLayout.tsx`, `BimViewer.tsx`) |

---

## Integração com bilds.com (implementada — fase 2 em progresso)

O ZIP gerado por este projeto é consumido pelo bilds.com. As rotas e componentes
React já existem em `/home/foltz/bilds.com/`:

**Rota pública:** `apps/web/src/app/[customLink]/[catalogSlug]/page.tsx`
- Server Component — busca `BimCatalogMeta` via `GET /b-bim-3d/{customLink}/{slug}`
- Carrega `catalog.json` do S3 e passa para `BimCatalogView`

**Componentes React em `apps/web/src/components/b-bim-3d/`:**
- `BimCatalogView.tsx` — roteador de layout (series-rows | catalog-grid)
- `CatalogGridLayout.tsx` — grid denso com filtros (Amanco)
- `SeriesRowsLayout.tsx` — rows Netflix por série (Dancor)
- `BimViewer.tsx` — viewer Three.js compartilhado (thumbnail + modal)
- `ProductModal.tsx` — modal de detalhes
- `CurveChart.tsx` — gráfico Q-H SVG
- `types.ts` — `BimCatalogData`, `BimProduct`, `BimCatalogMeta`

**Estado atual dos componentes React:**
- Sem hero section (ver plan-bim-catalog-hero-hover.md)
- `BimViewer.tsx` ainda usa click {once:true} para ativar rotação (ver mesmo plano)

**API NestJS** (`bilds.com/apps/api`):
- `GET /b-bim-3d/:customLink/:slug` — retorna meta + URLs S3
- `POST /companies/:id/bim-catalogs` — recebe ZIP, extrai, salva no S3

**Nota:** mudanças no bilds.com são feitas em sessões separadas naquele projeto.
Este repo (`bilds-bim-3d`) só produz o ZIP e o preview — não edita o bilds.com.

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
| Miniaturas só carregam ao clicar num filtro | Fix de timing ausente — adicionar `observeCards()` direto no init do módulo |
| Geo JSONs retornam 404 | Path relativo `./data/` em vez de absoluto `/data/` no fetchGeo |
| GPU trava | Loop de animação em todos os cards — usar padrão hover com flag `rotating` |
| Slug quebra caracteres portugueses | slugify sem NFKD — `ç→c` e `ã→a` precisam de normalização unicode antes do regex |
| interactive_config sobrescreve file_map correto | Chaves do config.json não batem com o que scan_input() gera — conferir slugify das categorias |
| scan_input() retorna 0 IFCs em subpastas | Usa os.listdir em vez de os.walk — corrigir para recursivo |
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
