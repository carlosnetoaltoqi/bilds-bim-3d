# Plano: hero section + hover 3D no catálogo BIM

**Contexto:** A página `/amanco/amanco-pvc-esgoto` está sem hero e sem rotação 3D no hover.
As mudanças foram desenvolvidas e validadas no template `bilds-bim-3d/templates/layouts/catalog-grid.html`.
Este plano porta essas mudanças para os componentes React em `apps/web/src/components/b-bim-3d/`.

---

## Arquivos alvo

| Arquivo | Mudança |
|---|---|
| `CatalogGridLayout.tsx` | Adicionar hero section |
| `SeriesRowsLayout.tsx` | Adicionar hero section |
| `BimViewer.tsx` | Trocar click → mouseenter/mouseleave (afeta ambos os layouts) |

---

## Mudança 1 — Hero section em `CatalogGridLayout.tsx`

**Problema atual:** a página começa com um `<h1>` simples e `<p>` de descrição. Sem identidade visual de fabricante.

**O que adicionar:** bloco hero antes da section atual com:
- Eyebrow: `{catalog.fabricante} · Biblioteca BIM · AltoQi Builder`
- Título h1 com `catalog.titulo` em Fira Sans
- Descrição `catalog.descricao`  
- Ficha de stats (dados disponíveis no `catalog` JSON):
  - Fabricante → `catalog.fabricante`
  - Produtos → `catalog.produtos.length`
  - Famílias → `catalog.filtros.length`
  - Formato → "IFC4" (fixo, sempre IFC4)

CSS de referência do `catalog-grid.html` (traduzir para style objects ou CSS-in-JS):

```css
.hero {
  background: linear-gradient(135deg, #002D72 0%, #00245B 100%);
  color: #fff;
  padding: 48px 24px 40px;
}
.eyebrow { font-size: 12px; font-weight: 600; letter-spacing: .08em; opacity: .7; text-transform: uppercase; margin-bottom: 16px; }
h1 { font-family: 'Fira Sans', sans-serif; font-size: clamp(28px, 5vw, 48px); font-weight: 700; line-height: 1.1; margin-bottom: 12px; }
.hero-ficha { display: flex; flex-wrap: wrap; gap: 24px 40px; margin-top: 28px; }
.ficha-row { display: flex; flex-direction: column; gap: 3px; }
.ficha-lbl { font-size: 11px; opacity: .6; text-transform: uppercase; letter-spacing: .06em; }
.ficha-val { font-size: 15px; font-weight: 600; }
```

React (inline styles):
```tsx
<div style={{
  background: 'linear-gradient(135deg, #002D72 0%, #00245B 100%)',
  color: '#fff',
  padding: '48px 24px 40px',
}}>
  <div style={{ maxWidth: 1200, margin: '0 auto' }}>
    <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '.08em', opacity: .7, textTransform: 'uppercase', marginBottom: 16 }}>
      {catalog.fabricante} · Biblioteca BIM · AltoQi Builder
    </div>
    <h1 style={{ fontFamily: "'Fira Sans', sans-serif", fontSize: 'clamp(28px,5vw,48px)', fontWeight: 700, lineHeight: 1.1, margin: '0 0 12px' }}>
      {catalog.titulo}
    </h1>
    {catalog.descricao && (
      <p style={{ fontSize: 15, opacity: .85, margin: '0 0 28px', maxWidth: 560 }}>{catalog.descricao}</p>
    )}
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px 40px' }}>
      {[
        { lbl: 'Fabricante', val: catalog.fabricante },
        { lbl: 'Produtos', val: String(catalog.produtos.length) },
        { lbl: 'Famílias', val: String(catalog.filtros.length) },
        { lbl: 'Formato', val: 'IFC4' },
      ].map(({ lbl, val }) => (
        <div key={lbl} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{ fontSize: 11, opacity: .6, textTransform: 'uppercase', letterSpacing: '.06em' }}>{lbl}</span>
          <span style={{ fontSize: 15, fontWeight: 600 }}>{val}</span>
        </div>
      ))}
    </div>
  </div>
</div>
```

Posicionar: logo antes do `<section>` atual (filtros + grid).

---

## Mudança 2 — Hero section em `SeriesRowsLayout.tsx`

**Problema atual:** igual ao `CatalogGridLayout` — começa com `<h1>` + `<p>` simples (linhas 153–165).

**Hero para series-rows** tem o mesmo estilo navy mas stats diferentes — Séries ao invés de Famílias, pois o agrupamento é por série:

```tsx
<div style={{
  background: 'linear-gradient(135deg, #002D72 0%, #00245B 100%)',
  color: '#fff',
  padding: '48px 24px 40px',
}}>
  <div style={{ maxWidth: 1200, margin: '0 auto' }}>
    <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '.08em', opacity: .7, textTransform: 'uppercase', marginBottom: 16 }}>
      {catalog.fabricante} · Biblioteca BIM · AltoQi Builder
    </div>
    <h1 style={{ fontFamily: "'Fira Sans', sans-serif", fontSize: 'clamp(28px,5vw,48px)', fontWeight: 700, lineHeight: 1.1, margin: '0 0 12px' }}>
      {catalog.titulo}
    </h1>
    {catalog.descricao && (
      <p style={{ fontSize: 15, opacity: .85, margin: '0 0 28px', maxWidth: 560 }}>{catalog.descricao}</p>
    )}
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px 40px' }}>
      {[
        { lbl: 'Fabricante', val: catalog.fabricante },
        { lbl: 'Modelos', val: String(catalog.produtos.length) },
        { lbl: 'Séries', val: String(catalog.filtros.length) },
        { lbl: 'Formato', val: 'IFC4' },
      ].map(({ lbl, val }) => (
        <div key={lbl} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{ fontSize: 11, opacity: .6, textTransform: 'uppercase', letterSpacing: '.06em' }}>{lbl}</span>
          <span style={{ fontSize: 15, fontWeight: 600 }}>{val}</span>
        </div>
      ))}
    </div>
  </div>
</div>
```

Posicionar: logo antes do `<section>` atual de filtros (linha 153), substituindo o bloco `<section>` com `<h1>` + `<p>`.

O bloco de filtros (`catalog.filtros.length > 0`) permanece, mas agora vem após o hero.

---

## Mudança 3 — Hover 3D em `BimViewer.tsx` (modo thumbnail)

**Problema atual** (linhas 124–133):
```typescript
controls.autoRotate = false
renderer.render(scene, camera)
canvas.addEventListener(
  'click',
  () => {
    controls.autoRotate = true
    animate()
  },
  { once: true }
)
```

**Padrão correto** (do `catalog-grid.html`):
- `mouseenter` → cria loop se ainda não existe, seta `rotating = true`, inicia spin
- `mouseleave` → seta `rotating = false`, render um frame estático (para o loop na próxima iteração)
- Loop verifica `rotating` antes de agendar o próximo frame

**Implementação:**

No `useEffect`, substituir o bloco de `mode !== 'modal'` por:

```typescript
if (mode === 'modal') {
  animate()
} else {
  // render estático inicial
  renderer.render(scene, camera)

  let rotating = false
  let rafId = 0

  function spin() {
    if (!rotating) { rafId = 0; return }
    rafId = requestAnimationFrame(spin)
    controls.update()
    renderer.render(scene, camera)
  }

  canvas.addEventListener('mouseenter', () => {
    rotating = true
    if (!rafId) spin()
  })
  canvas.addEventListener('mouseleave', () => {
    rotating = false
    renderer.render(scene, camera) // freeze frame
  })

  stateRef.current = { renderer, controls, raf: rafId }
}
```

O cleanup do `useEffect` (já existente) cancela o RAF e descarta o renderer normalmente.

**Também:** remover `cursor: pointer` do canvas em modo thumbnail — não há mais ação no click:
```typescript
// linha 158: trocar
cursor: mode === 'thumbnail' ? 'pointer' : 'grab',
// por:
cursor: 'default',
```

---

## Mudança 4 — `stateRef` e cleanup (ajuste menor)

O `stateRef.current.raf` no cleanup atual chama `cancelAnimationFrame(stateRef.current.raf)`. 
Com o padrão `rotating`, o `raf` muda a cada frame. O cleanup precisa:
1. Setar `rotating = false` para interromper o loop naturalmente
2. OU manter o cancelAnimationFrame com o último `rafId` conhecido

A solução mais simples: usar uma variável `cancelled` (já existe no código) para parar o loop:

```typescript
function spin() {
  if (!rotating || cancelled) { rafId = 0; return }
  rafId = requestAnimationFrame(spin)
  controls.update()
  renderer.render(scene, camera)
}
```

O `cancelled = true` no cleanup existente (linha 71) já para o loop.

---

## Verificação após as mudanças

Testar ambos os layouts:

1. `http://localhost:3000/amanco/amanco-pvc-esgoto` (layout `catalog-grid`)
   - Hero navy com "Amanco · Biblioteca BIM · AltoQi Builder", título, descrição e stats
   - Hover no card → gira; sair do card → para (freeze frame)
   - Hover novamente → volta a girar sem recarregar o modelo
   - Abrir modal → viewer grande gira automaticamente

2. `http://localhost:3000/dancor/dancor-bombas-incendio` (layout `series-rows`, se existir)
   - Mesma verificação do hero
   - Rows Netflix por série com hover funcionando nos cards
