---
name: pagina-biblioteca
description: Constrói páginas de catálogo BIM com cards de produto, miniaturas 3D estáticas (click-to-activate), viewer 3D no modal, curvas Q-H em SVG e layout responsivo. Padrões validados em produção com Three.js self-hosted.
version: 1.8.0
author: Bilds / carlosnetoaltoqi
---

> Os documentos de `docs/conhecimento/` citados abaixo também estão em `referencias/` (symlink), para que esta skill leve o conhecimento junto quando usada fora do repositório.

# Skill: pagina-biblioteca

Você é especialista em construir páginas de catálogo BIM — cards de produto, miniatura 3D estática com click-to-activate, viewer 3D no modal, curva Q-H em SVG, layout responsivo. Os padrões valem tanto para HTML puro quanto para um viewer dentro de um framework (React etc.) — o que muda é onde cada peça mora.

Ao ser invocada, pergunte:
1. Onde estão os JSONs de geometria (resultado de `leitor-ifc`/`leitor-step`) e os dados de produto (resultado de `leitor-biblioteca-aq` ou de um plugin de catálogo)?
2. A página roda em HTML puro ou dentro de um framework?
3. Onde ela será hospedada (determina a estratégia de CSP para scripts externos)?
4. Quais são os tokens visuais (cor, tipografia, radius)? **São do consumidor** — pergunte, não invente uma paleta.

## Quando usar

- Montar ou revisar a página (ou os componentes) de um catálogo BIM: grade de produtos, linhas por série, modal com viewer 3D, curva Q-H.
- Diagnosticar performance de miniatura (o elemento LCP costuma ser ela) ou 404 de asset em produção.

## Workflow

1. Escolher o layout por catálogo: grade densa com filtro (`catalog-grid`) ou linhas por série (`series-rows`).
2. Renderizar cada card com uma miniatura **estática** (um frame, sem loop de animação) e ativar o 3D só ao clicar — nunca um `requestAnimationFrame` por card visível.
3. Compartilhar UM renderer Three.js entre cards (um por card estoura o limite de contexto WebGL); no build, pré-renderizar as miniaturas com o mesmo código do runtime, no mesmo harness, em Chromium headless.
4. No modal, subir o viewer 3D completo (OrbitControls) a partir do mesmo cache de geometria; desenhar a curva Q-H em SVG inline quando o produto tiver `curva`.
5. Servir os vendors (Three.js) self-hosted, nunca de CDN externo, se a página for pública.
6. Conferir por screenshot (nunca por `readPixels` sem `preserveDrawingBuffer`) e checar `r.ok` antes de `JSON.parse` em todo fetch de asset.

## Armadilhas essenciais (uma linha cada)

- Um renderer/contexto WebGL por card não escala (limite de ~8–16 no browser) — use um renderer compartilhado e capture para imagem.
- Miniatura dinâmica no primeiro paint é o próprio LCP da página — pré-renderize no build com o mesmo harness que roda em runtime.
- Caminho de asset relativo quebra sob `cleanUrls`/rotas sem barra final — use caminho absoluto a partir da raiz do catálogo.
- Nome de série com aspas (polegadas) quebra atributo/`onclick` sem escape — use o autoescape do template engine e leia o filtro do `dataset`, nunca monte JS inline com o valor cru.
- Passar geometria como **objeto** para `page.evaluate` do Playwright custa vários múltiplos a mais que passar como string JSON.
- Estado do card (ativado ou não) é por item — reinicializar tudo a cada re-render perde o que o usuário já ativou.
- Os tokens visuais (cor, radius, fonte) são do consumidor da skill — não fixe uma paleta de marca aqui.

## Pontos de entrada neste repo

Aqui a página é um viewer React (não HTML estático) em `web/src/components/bim-catalog/`:

- `BimCatalogView.tsx` — escolhe o layout (`CatalogGridLayout` ou `SeriesRowsLayout`) a partir de `catalog.layout`.
- `LazyBimCard.tsx` — lazy load (`IntersectionObserver`) + miniatura estática + ativação por clique.
- `bim-viewer-engine.ts` — cache de geometria (`fetchGeo`), montagem de cena Three.js, captura de miniatura (renderer compartilhado).
- `BimViewer.tsx` — viewer 3D nos dois modos (`thumbnail`/`modal`, com `OrbitControls` no modal).
- `ProductModal.tsx`, `CurveChart.tsx` — modal de produto e curva Q-H em SVG.
- `types.ts` — o contrato de produto/catálogo que a página consome.
- Harness de pré-render, mesmo código para build e serviço: `biblioteca/bim_pipeline/miniaturas/` — `render.py` (chama o Node), `thumbs.mjs` (sobe um servidor efêmero + Chromium/Playwright), `harness.html` (a mesma `buildScene()` do viewer).

## Leia antes (docs/conhecimento/)

| Tópico | Doc |
|---|---|
| Miniatura estática + click-to-3D, renderer compartilhado, pré-render no build, harness único para build e serviço | `miniaturas.md` |
| Contrato de geometria `{pos,col,idx}`, cache | `geometria.md` |
| Modelo do catálogo (produto, specs, layouts) | `catalogo-modelo.md` |
| Dados hidráulicos e curva Q-H (de onde vêm) | `aq-formato.md` |
| Conteúdo do ZIP para publicação | `zip-bilds-formato.md` |
| Processos filhos (Chromium/Playwright órfão, stdin/EOF) | `processos-filhos.md` |
| Diagnóstico rápido | `diagnostico.md` |
