---
name: pagina-biblioteca
description: Constrói páginas HTML de catálogo BIM com cards de produto, miniaturas 3D estáticas (click-to-activate), viewer 3D no modal, curvas Q-H em SVG e layout responsivo. Padrões validados em produção com Three.js self-hosted.
version: 1.2.0
author: Bilds / carlosnetoaltoqi
---

# Skill: pagina-biblioteca

Você é especialista em construir páginas de catálogo BIM em HTML puro (sem framework/build), com visualização 3D de modelos IFC usando Three.js. Esta skill cobre os padrões que funcionam em produção, incluindo as armadilhas encontradas.

Ao ser invocada, pergunte ao usuário:
1. Qual o design system ou referência visual a seguir?
2. Onde ficam os arquivos JSON de geometria? (resultado do `leitor-ifc`)
3. Quais dados de produto existem? (resultado do `leitor-biblioteca-aq` ou similar)
4. A página será hospedada onde? (determina a estratégia de CSP para scripts externos)

---

## Arquitetura da página

### Por que HTML puro

Páginas de catálogo BIM são estáticas: dados fixos, sem autenticação, sem servidor. HTML puro com `cleanUrls` na Vercel elimina todo overhead de build. Qualquer arquivo `.html` na raiz do diretório vira uma rota diretamente.

### Dois scripts, uma página

A divisão obrigatória entre sync e module resolve o problema de timing do Three.js:

```html
<!-- Script 1: sync — roda durante o parse, renderiza os cards no DOM -->
<script>
const ITEMS = [...];        // dados dos produtos
function buildCard(item) {} // gera HTML string
function openModal(id) {}   // popula e abre o modal
renderItems('all');         // chama buildCard, insere no DOM, dispara evento
</script>

<!-- Script 2: module — roda após DOMContentLoaded, acessa os canvases -->
<script type="module">
import * as THREE from '/vendor/three.module.js';
import { OrbitControls } from '/vendor/OrbitControls.js';
// ouve 'cards-rendered' antes de procurar os canvases no DOM
document.addEventListener('cards-rendered', e => observeCards());
</script>
```

O script sync dispara um `CustomEvent('cards-rendered')` ao terminar de renderizar:
```javascript
function renderItems(filter) {
  // ... buildCard + innerHTML
  document.dispatchEvent(new CustomEvent('cards-rendered', { detail: { items } }));
}
```

Sem esse handshake, o módulo Three.js tenta acessar `<canvas>` que ainda não existe no DOM.

---

## Three.js self-hosted — obrigatório em produção Vercel

A Vercel aplica CSP `script-src 'self' 'unsafe-inline'` que bloqueia qualquer CDN externo. CDNs como `cdn.jsdelivr.net`, `unpkg.com` e `cdnjs.cloudflare.com` são bloqueados silenciosamente — o script não carrega, sem erro visível no console da página.

**Solução:** baixar e servir Three.js localmente:

```
projeto/
└── vendor/
    ├── three.module.js      ← baixar de três releases no GitHub
    └── OrbitControls.js     ← de three/examples/jsm/controls/
```

**Importmap no `<head>` — obrigatório antes de qualquer `<script type="module">`:**
```html
<script type="importmap">
  {"imports":{"three":"/vendor/three.module.js"}}
</script>
```

Sem o importmap, o `import * as THREE from 'three'` falha com "bare specifier" não resolvido. O importmap deve vir **antes** de qualquer script module na página.

**No módulo:**
```javascript
import * as THREE from 'three';                           // resolve via importmap
import { OrbitControls } from '/vendor/OrbitControls.js'; // path absoluto direto
```

---

## Padrão de miniatura estática + click-to-3D

Não inicialize todos os viewers simultanamente — GPU explode com 10+ contextos WebGL ativos.

### IntersectionObserver para lazy load

```javascript
const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) { loadThumbnail(e.target.dataset.id); io.unobserve(e.target); }
  });
}, { rootMargin: '120px' }); // 120px antes de entrar na viewport

document.querySelectorAll('.card[data-id]').forEach(card => io.observe(card));
```

### Render estático (um frame, sem loop)

```javascript
async function loadThumbnail(itemId) {
  const canvas = document.getElementById('canvas-' + itemId);
  const W = canvas.parentElement.offsetWidth || 224;
  const H = canvas.parentElement.offsetHeight || 162;

  const data = await fetch('/data/' + geoFile + '.json').then(r => r.json());

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); // cap em 1.5x nos cards
  renderer.setSize(W, H, false);
  renderer.setClearColor(0xFAFBFB, 1);

  const { scene, size } = buildScene(data);
  const camera = new THREE.PerspectiveCamera(38, W / H, 0.001, 500);
  camera.position.set(size * 0.85, size * 0.32, size * 0.85);
  camera.lookAt(0, 0, 0);

  renderer.render(scene, camera); // UM frame — para aqui
  // canvas mostra imagem estática até o usuário clicar
}
```

### Ativar ao clicar

```javascript
canvas.addEventListener('click', () => {
  const controls = new OrbitControls(camera, canvas);
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.2;
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.enableZoom = false;
  controls.enablePan = false;

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}, { once: true }); // { once: true } garante que só ativa uma vez

canvas.style.cursor = 'pointer';
```

### Um renderer por card NÃO escala — use shared renderer + captura JPEG

O padrão acima (um `WebGLRenderer` por card, criado no `IntersectionObserver`) quebra em catálogos grandes. O browser limita a **~8–16 contextos WebGL simultâneos**; ao rolar a página, os mais antigos são descartados e as miniaturas **somem**:

```
WARNING: Too many active WebGL contexts. Oldest context will be lost.
```

A solução é não manter contexto nenhum por card:

- **`sharedRenderer`** — um único `WebGLRenderer` com `preserveDrawingBuffer: true`, criado sob demanda e reutilizado sequencialmente por todos os thumbnails.
- Depois de renderizar: `canvas.toDataURL('image/jpeg', 0.88)` → `<img>`. Zero contextos persistentes.
- **`thumbCache (Map<id, dataURL>)`** — sobrevive aos filtros, que destroem e recriam o DOM. Card que volta é restaurado do cache, sem re-render.
- **`renderQueue` + `processQueue`** — fila sequencial, um render por vez.
- **`activeCard`** — o viewer interativo (OrbitControls + loop) só ao clicar; o `IntersectionObserver` o desativa ao sair da viewport e restaura o thumb.
- **`disposeScene`** — libera geometrias e materiais da GPU após cada thumbnail.

Resultado: **no máximo 3 contextos WebGL** em qualquer momento — `sharedRenderer`, `activeCard.renderer` e `modalViewer.renderer`.

### Estado por item — evitar reinicialização

Use um `Map` para guardar o estado de cada viewer:
```javascript
const thumbStates = new Map();
// thumbStates.get(itemId) = { renderer, scene, camera, controls, animated: false }
// Verificar antes de iniciar: if (thumbStates.has(itemId)) return;
```

Quando o usuário filtra e os cards são re-renderizados, limpar viewers órfãos:
```javascript
thumbStates.forEach((state, id) => {
  if (!document.getElementById('canvas-' + id)) {
    cancelAnimationFrame(state.raf);
    state.controls?.dispose();
    state.renderer.dispose();
    thumbStates.delete(id);
  }
});
```

### `observeCards()` no carregamento inicial, não só no evento

O `cards-rendered` dispara no script síncrono, durante o parse do HTML. O listener no módulo ES só é registrado depois — chega tarde e o primeiro lote de cards nunca é observado (as miniaturas só aparecem após o primeiro clique num filtro).

Chame `observeCards()` **direto**, logo após registrar o listener, e mantenha o listener para os re-renders da filtragem.

---

## Cache de geometria

Nunca fazer dois fetches do mesmo JSON. Um `Map` resolve — **com a chave sendo a URL**, não o id do produto: peças diferentes costumam compartilhar a mesma malha (variantes que mudam só em dados), e cachear por URL faz o arquivo ser baixado uma vez só.

```javascript
const geoCache = new Map();

// Caminho ABSOLUTO derivado do slug, nunca './data/'
const DATA_BASE = '/' + CATALOG.slug + '/data/';

async function fetchGeo(geoFile) {
  if (geoCache.has(geoFile)) return geoCache.get(geoFile);
  const data = await fetch(DATA_BASE + geoFile).then(r => {
    if (!r.ok) throw new Error(`${r.status} ao buscar ${geoFile}`);
    return r.json();
  });
  geoCache.set(geoFile, data);
  return data;
}
```

### Duas armadilhas nesse fetch

**1. `./data/` quebra com `cleanUrls`.** Com `cleanUrls: true` a Vercel serve a página em `/<slug>` — **sem barra final**. Um caminho relativo resolve a partir do diretório pai, ou seja, a raiz do site:

```
página: /sensor-alarme
./data/x.json  →  /data/x.json              404
o arquivo está →  /sensor-alarme/data/x.json  200
```

Use caminho absoluto montado a partir do slug: funciona com ou sem barra final, local e em produção. Manter a geometria dentro do diretório do catálogo também evita colisão de nomes entre catálogos — `50mm.json` se repete em toda biblioteca de conexões.

**2. Sem checar `r.ok`, o erro mente.** Um 404 devolve a página de erro em HTML, que cai no `JSON.parse` e vira:

```
SyntaxError: Unexpected token 'T', "The page c"... is not valid JSON
```

O `'T'` é de "**T**he page could not be found". Perde-se o status real e o diagnóstico vai para o lado errado. Sempre cheque `r.ok` e inclua o nome do arquivo na mensagem.

---

## Construção de cena Three.js a partir do JSON

```javascript
function buildScene(data) {
  const scene = new THREE.Scene();

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));

  // Guard: col pode ser [] para IFCs sem IFCINDEXEDCOLOURMAP (conexões, fittings)
  const hasCol = data.col && data.col.length > 0;
  if (hasCol) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));

  // Guard: idx está ausente em geometria expandida (quando há cores por face)
  if (data.idx) geom.setIndex(data.idx);

  geom.computeVertexNormals();
  geom.computeBoundingBox();
  const center = geom.boundingBox.getCenter(new THREE.Vector3());
  const size   = geom.boundingBox.getSize(new THREE.Vector3()).length();

  // vertexColors: true ativa cores por vértice — color base deve ser 0xffffff
  // (Three.js multiplica: branco × cor do vértice = cor original).
  // Sem cores: usar cinza industrial 0x8896AA.
  const mat = new THREE.MeshStandardMaterial({
    vertexColors: hasCol,
    color: hasCol ? 0xffffff : 0x8896AA,
    metalness: 0.3,
    roughness: 0.6,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.position.copy(center.negate());
  scene.add(mesh);

  // Iluminação 3-pontos para peças industriais
  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const key = new THREE.DirectionalLight(0xffffff, 0.95);
  key.position.set(2, 3, 2); scene.add(key);
  const fill = new THREE.DirectionalLight(0xC8D8F0, 0.35);
  fill.position.set(-2, 1, -1); scene.add(fill);

  return { scene, size };
}
```

`size` (diagonal da bounding box) posiciona a câmera proporcionalmente — funciona para qualquer escala de equipamento.

---

## Viewer 3D no modal

O modal usa um canvas separado com qualidade maior. Inicializa ao abrir, descarta ao fechar.

```javascript
let modalViewer = null;

async function initModalViewer(item) {
  // Descartar viewer anterior
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }

  const canvas = document.getElementById('modal-canvas');
  const W = canvas.parentElement.offsetWidth || 760;
  const H = canvas.parentElement.offsetHeight || 340;

  const data = await fetchGeo(item.geo); // usa o cache — sem segundo fetch

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); // 2x no modal — mais qualidade
  renderer.setSize(W, H, false);
  renderer.setClearColor(0xF3F4F6, 1);

  const { scene, size } = buildScene(data);
  const camera = new THREE.PerspectiveCamera(34, W / H, 0.001, 500);
  camera.position.set(size * 0.9, size * 0.35, size * 0.9);
  camera.lookAt(0, 0, 0);

  const controls = new OrbitControls(camera, canvas);
  controls.autoRotate = true; controls.autoRotateSpeed = 0.7;
  controls.enableDamping = true; controls.dampingFactor = 0.06;
  controls.enableZoom = true; // modal pode ter zoom, card não
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

// Ao fechar o modal:
document.addEventListener('modal-closed', () => {
  if (modalViewer) {
    cancelAnimationFrame(modalViewer.raf);
    modalViewer.controls?.dispose();
    modalViewer.renderer.dispose();
    modalViewer = null;
  }
});
```

---

## Curva Q-H em SVG inline

Gerada dinamicamente a partir de pontos `[vazao, altura, potencia, rendimento]`:

```javascript
function buildChart(pts, W=300, H=180) {
  if (!pts?.length) return '<p>Curva não disponível.</p>';
  const pl=40, pr=12, pt=14, pb=36;
  const cW=W-pl-pr, cH=H-pt-pb;
  const qMax = Math.max(...pts.map(p=>p[0])) * 1.1;
  const hMax = Math.max(...pts.map(p=>p[1])) * 1.18;

  const tx = q => pl + (q/qMax)*cW;
  const ty = h => H - pb - (h/hMax)*cH;

  // Grid
  let g = '';
  [.25,.5,.75,1].forEach(f => {
    const yy = ty(hMax*f).toFixed(1);
    g += `<line x1="${pl}" y1="${yy}" x2="${W-pr}" y2="${yy}" stroke="#E5E7EB" stroke-width="1"/>`;
    g += `<text x="${pl-5}" y="${+yy+3}" text-anchor="end" fill="#6B7280" font-size="9">${Math.round(hMax*f)}</text>`;
  });

  // Curva Q-H com área preenchida
  const path = 'M' + pts.map(p=>`${tx(p[0]).toFixed(1)},${ty(p[1]).toFixed(1)}`).join('L');
  const area = path + `L${tx(pts.at(-1)[0]).toFixed(1)},${H-pb}L${tx(pts[0][0]).toFixed(1)},${H-pb}Z`;

  // Curva de rendimento (tracejada, eixo secundário 0-65%)
  const tyEff = e => H - pb - (Math.min(e,65)/65)*cH;
  const eff = 'M' + pts.map(p=>`${tx(p[0]).toFixed(1)},${tyEff(p[3]).toFixed(1)}`).join('L');

  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    <rect x="${pl}" y="${pt}" width="${cW}" height="${cH}" fill="#FAFBFB" rx="2"/>
    ${g}
    <path d="${area}" fill="rgba(30,64,175,0.1)"/>
    <path d="${path}" fill="none" stroke="#1E40AF" stroke-width="2" stroke-linejoin="round"/>
    <path d="${eff}" fill="none" stroke="#9CA3AF" stroke-width="1.5" stroke-dasharray="4,3"/>
    <text x="${pl+cW/2}" y="${H-2}" text-anchor="middle" fill="#9CA3AF" font-size="9">Vazão (m³/h)</text>
  </svg>`;
}
```

---

## Estrutura do card

```javascript
function buildCard(item) {
  return `<div class="card" data-id="${item.id}" data-geo="${item.geo}"
               role="button" tabindex="0"
               aria-label="Ver detalhes ${item.nome}">
    <!-- Canvas container: altura fixa, posição relativa para o badge -->
    <div class="card-canvas-wrap">
      <canvas id="canvas-${item.id}"></canvas>
      <div class="card-canvas-loader" id="loader-${item.id}">Carregando…</div>
      <!-- Badge 3D — canto superior direito, some ao ativar -->
      <div class="card-3d-badge" id="cta-${item.id}" role="button" aria-label="Ver em 3D">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
             stroke="#FF4F1F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
      </div>
    </div>
    <div class="card-body">
      <!-- conteúdo: nome, specs, botão -->
    </div>
  </div>`;
}
```

CSS do badge:
```css
.card-3d-badge {
  position: absolute; top: 8px; right: 8px;
  width: 30px; height: 30px;
  background: rgba(255,255,255,0.93);
  border-radius: 4px; /* seguir o radius do DS */
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; z-index: 2;
  transition: background .15s, opacity .25s;
}
.card-3d-badge:hover { background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.card-3d-badge.off { opacity: 0; pointer-events: none; }
```

---

## Rows estilo Netflix

```css
.row-track {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 4px 0 16px;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.row-track::-webkit-scrollbar { display: none; }
.card { scroll-snap-align: start; flex-shrink: 0; width: 224px; }

/* Fade nas bordas sinalizando overflow */
.row-outer { position: relative; }
.row-outer::before, .row-outer::after {
  content: ''; position: absolute; top: 0; bottom: 16px; width: 28px;
  z-index: 10; pointer-events: none;
}
.row-outer::before { left: 0; background: linear-gradient(to right, var(--bg), transparent); }
.row-outer::after  { right: 0; background: linear-gradient(to left, var(--bg), transparent); }
```

---

## Modal

```css
.modal-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0.5); backdrop-filter: blur(4px);
  display: none; align-items: center; justify-content: center; padding: 16px;
}
.modal-backdrop.open { display: flex; }
.modal {
  background: #fff; border-radius: 4px;
  width: 100%; max-width: 820px; max-height: 92vh;
  overflow-y: auto; display: flex; flex-direction: column;
  animation: slideUp .2s ease;
}
@keyframes slideUp { from { transform: translateY(12px); opacity: 0; } to { transform: none; opacity: 1; } }

/* Cabeçalho e rodapé sticky dentro do modal com scroll */
.modal-head, .modal-actions {
  position: sticky; background: #fff; z-index: 10;
}
.modal-head { top: 0; }
.modal-actions { bottom: 0; }
```

Estrutura interna:
1. `.modal-head` — sticky top: título + botão fechar
2. `.modal-3d-wrap` — canvas do viewer grande (340px desktop, 240px mobile)
3. `.modal-body` — grid 2 colunas: gráfico | specs (1 coluna no mobile)
4. `.modal-actions` — sticky bottom: CTAs

Fechar ao clicar no backdrop ou pressionar Escape:
```javascript
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
```

---

## Responsividade

Breakpoints que funcionam para cards de catálogo BIM:

```css
/* Cards */
@media (max-width: 480px) { .card { width: 196px; } }
@media (max-width: 480px) { .card-canvas-wrap { height: 142px; } }

/* Modal */
@media (max-width: 600px) {
  .modal-3d-wrap { height: 240px; }      /* viewer menor no mobile */
  .modal-body { grid-template-columns: 1fr; } /* specs empilham */
}

/* Hero (se tiver imagem de produto) */
@media (max-width: 640px) {
  .hero-img { display: none; }           /* imagem some, texto ocupa tudo */
  .hero::after { background: none; }    /* remove gradiente de legibilidade */
}

/* Topbar */
@media (max-width: 860px) { .topbar-nav { display: none; } }
@media (max-width: 520px) { .tb-outline { display: none; } /* oculta botão secundário */ }

/* Filter chips: scroll horizontal em vez de quebrar linha */
@media (max-width: 480px) {
  .filter-bar {
    flex-wrap: nowrap; overflow-x: auto; padding-bottom: 4px;
    -webkit-overflow-scrolling: touch; scrollbar-width: none;
  }
}
```

---

## Filtro dinâmico sem re-fetch

Filtros por categoria operam sobre os dados em memória — sem request:

```javascript
function matchesFilter(item, f) {
  if (f === 'all') return true;
  // filtros por tipo, faixa numérica etc.
  return item.tipo === f;
}

function renderItems(filter) {
  const wItems = ITEMS.filter(i => matchesFilter(i, filter));
  document.getElementById('track').innerHTML = wItems.map(buildCard).join('');
  // Re-observar novos cards
  observeCards();
  document.dispatchEvent(new CustomEvent('cards-rendered', { detail: { items: wItems } }));
}
```

Ao filtrar, os cards antigos são destruídos. Limpar viewers órfãos antes do IntersectionObserver reobservar — ver "Estado por item" acima.

---

## Dois layouts de catálogo

### series-rows — linhas estilo Netflix (ex: Dancor, bombas)

Para catálogos com poucas famílias (2–4) e muitas variantes por família. Agrupa produtos por
`produto.serie`, renderiza uma linha horizontal com scroll por série. Ideal quando há curva Q-H.

```javascript
// Agrupamento por série
const bySerie = {};
ITEMS.forEach(i => {
  const s = i.serie || 'Outros';
  if (!bySerie[s]) bySerie[s] = [];
  bySerie[s].push(i);
});
// Renderiza uma seção por série
Object.entries(bySerie).forEach(([serie, items]) => renderSection(serie, items));
```

### catalog-grid — grade densa com filtros (ex: Amanco, conexões)

Para catálogos com muitos itens heterogêneos (20+). Mostra chips de filtro no topo que filtram
por `produto.serie`. Sem agrupamento em seções — todos os cards em grid uniforme.

```javascript
// Chips de filtro — gerados a partir de catalog.filtros
catalog.filtros.forEach(f => {
  const btn = document.createElement('button');
  btn.className = 'chip';
  btn.textContent = f;
  btn.onclick = () => renderGrid(f);
  filterBar.appendChild(btn);
});

// Filtro opera em memória
function renderGrid(filter) {
  const filtered = ITEMS.filter(i => filter === 'all' || i.serie === filter);
  gridEl.innerHTML = filtered.map(buildCard).join('');
  document.dispatchEvent(new CustomEvent('cards-rendered'));
}
```

**Diferença chave:** `catalog-grid` filtra por `produto.serie` usando chips;
`series-rows` agrupa por `produto.serie` em linhas separadas.
Ambos usam o mesmo `buildScene`, `loadThumbnail`, `initModalViewer` e `buildChart`.

---

## Armadilhas encontradas em produção

| Problema | Causa | Solução |
|---|---|---|
| Three.js não carrega (sem erro) | CDN bloqueado por CSP Vercel | Self-host em `/vendor/`, usar importmap |
| `import * as THREE from 'three'` falha | Importmap ausente ou fora de ordem | Colocar `<script type="importmap">` antes de qualquer module script |
| Canvas não encontrado no init do módulo | Módulo roda antes dos cards serem renderizados | Usar `CustomEvent('cards-rendered')` como handshake |
| GPU trava com 10+ viewers | Loop de animação em todos simultâneos | Thumbnail estática + loop só após click |
| Viewer do modal usa geometria errada | Modal não limpou viewer anterior | Guard `if (modalViewer !== mv) return` no loop de animação |
| Filtrar recria cards, viewers re-iniciam | `thumbStates` não foi limpo antes | Limpar estados órfãos antes de re-observar |
| Canvas tem tamanho errado em mobile | `offsetWidth` retorna 0 antes do layout | Fallback: `const W = wrap.offsetWidth \|\| 224` |
| `cleanUrls` funciona na Vercel mas não local | Comportamento de servidor | Localmente usar extensão `.html`; na Vercel a rota sem extensão funciona |
| `data/*.json` dá 404 na Vercel, ok local | `cleanUrls` serve a página em `/<slug>` sem barra final — `./data/` resolve para a raiz | Caminho absoluto: `'/' + CATALOG.slug + '/data/'` |
| `SyntaxError: Unexpected token 'T'` | 404 devolveu HTML e caiu no `JSON.parse` ("**T**he page…") | Checar `r.ok` antes de `.json()` |
| Miniaturas somem ao rolar a página | Estouro de contextos WebGL (limite ~8–16) | `sharedRenderer` + `toDataURL` → `<img>`; ver "shared renderer" |
| Miniaturas só aparecem após clicar num filtro | `observeCards()` chamado só no listener de `cards-rendered`, que chega tarde | Chamar também direto, no carregamento |
| Mesmo JSON baixado várias vezes | Cache com chave por produto, e peças compartilham malha | Cachear por URL |

---

## Histórico

**1.2.0** — Shared renderer + captura JPEG para catálogos grandes (o padrão de um renderer por card estoura o limite de contextos WebGL). Caminho absoluto para a geometria, obrigatório com `cleanUrls`. Checagem de `r.ok` antes do `JSON.parse`. Cache de geometria por URL, já que peças diferentes compartilham malha. Validado em produção com 9 catálogos, o maior com 856 produtos.

**1.1.0** — Padrões de card, modal, curva Q-H em SVG e os dois layouts de catálogo.
