# Plano: atualizar series-rows.html com padrão hover 3D

Arquivo alvo: `templates/layouts/series-rows.html`

Referência já atualizada: `templates/layouts/catalog-grid.html`

---

## Mudança 1 — Click → mouseenter/mouseleave no `loadThumbnail`

Localizar (linhas ~426-446):

```javascript
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
```

Substituir por:

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
  renderer.render(scene, camera);
});
```

---

## Mudança 2 — Fix de timing: `observeCards()` direto no init do módulo

Localizar (linha ~522):

```javascript
document.addEventListener('cards-rendered', () => observeCards());
document.addEventListener('modal-open', e => initModalViewer(e.detail.id));
```

Adicionar chamada direta após o listener:

```javascript
document.addEventListener('cards-rendered', () => observeCards());
document.addEventListener('modal-open', e => initModalViewer(e.detail.id));
observeCards(); // cards já estão no DOM quando o módulo carrega
```

---

## Mudança 3 — Remover CSS residual do topbar

Localizar (linha ~173):

```css
.topbar{padding:0 16px}
```

Remover essa linha.

---

## Verificação final

Após as edições, confirmar:

```bash
grep -n "click.*once\|once.*true" templates/layouts/series-rows.html
# deve retornar vazio (nenhum click {once:true} restante nos canvases)

grep -n "mouseenter\|mouseleave" templates/layouts/series-rows.html
# deve mostrar as 2 novas linhas dentro de loadThumbnail

grep -n "observeCards()" templates/layouts/series-rows.html
# deve mostrar 2 linhas: o listener + a chamada direta

grep -n "topbar" templates/layouts/series-rows.html
# deve retornar vazio
```
