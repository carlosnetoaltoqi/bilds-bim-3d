# 2026-08-24 — Bug WebGL: shared renderer + JPEG capture (commits 888652b, 0a39225)

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

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

**Bug 12 — `observeCards()` não chamado no carregamento inicial (commit 0a39225)**

O evento `cards-rendered` disparava no script síncrono (durante o parse do HTML), mas
o listener no módulo ES só registrava após `DOMContentLoaded` — chegava tarde demais.
Resultado: Amanco não carregava miniaturas até o primeiro clique em filtro.

Correção: adicionar `observeCards()` direto após o `addEventListener` no módulo, além
de manter o listener para re-renders (ao filtrar).

**Ponto estável: commit `0a39225`** — WebGL context overflow resolvido, validado em produção.
Para retornar: `git checkout 0a39225`.
