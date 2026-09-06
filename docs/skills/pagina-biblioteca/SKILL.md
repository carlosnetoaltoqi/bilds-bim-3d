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

## Histórico

**1.8.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para `docs/conhecimento/miniaturas.md`, `geometria.md`, `catalogo-modelo.md` e `processos-filhos.md`; removida a cor de marca fixa dos exemplos de card — os tokens visuais são do consumidor da skill; sem nomes de fabricantes (ADR-016).

**1.7.0** — Jinja2 passa a ser obrigatório no gerador: o "fallback" sem Jinja2 entregava a página
com `{% for %}` cru e nenhum card, e o chamador ignorava o `False`. Regra nova na seção de chips:
sem o motor de template, falhe alto antes de escrever qualquer arquivo (bilds-bim-3d, I7, 2026-09-04).

**1.6.0** — Nomes de série com aspas (`1" x 1"`, `"T" Horizontal`) quebravam os chips de
filtro em 6 catálogos gerados pelo `bilds-bim-3d`: atributo truncado, `onclick` com erro de
sintaxe, e nenhum aviso no build. Corrigido com `autoescape=True` no Jinja2 e handler que
lê `this.dataset.filter`. Verificado com Playwright clicando o chip nas duas variantes de
layout. Nova subseção em "catalog-grid" e linha na tabela de armadilhas.

**1.5.0** — Duas armadilhas de **verificação** de página gerada, ambas encontradas ao
conferir um catálogo de 262 peças. (a) O `/vendor/` do importmap é root-relative: mover o
diretório do catálogo quebra o import sem erro no console, e o card fica em branco igual a
"geometria não chegou" — quem realoca tem de levar o `vendor/` como irmão e servir esse
nível como raiz. (b) **Não confira o render lendo pixel com `readPixels`**: o renderer da
página não usa `preserveDrawingBuffer`, então a leitura volta zerada mesmo com a peça na
tela — reportou 0 de 263 canvas pintados numa página em que as 262 peças estavam
visíveis. Conferir por screenshot e olhar a imagem.

**1.4.0** — **O mesmo harness serve build e servidor de aplicação.** Extrair a função que
toca WebGL (`renderThumbFromData`, recebe a geometria em memória) e deixar a versão por URL
como wrapper permite que um backend gere as miniaturas com o mesmo código do build.
Documentada a armadilha que dominava o tempo — passar a geometria como **objeto** para
`page.evaluate` custa 6× mais que passar como string JSON (2 200 ms × 370 ms por
miniatura), porque o serializador do Playwright anda o grafo. Também: singleton de browser
com fechamento explícito antes do `process.exit()`, a exigência de `http://` (o importmap
não sobrevive a `file://`), a medição que mostra que r170 × r185 é indiferente (PSNR 71 dB),
e a armadilha de cache ao regenerar miniatura na mesma URL. Números novos para a decisão
"não rasterize em código": 27 dB do rasterizador software × 47 dB do harness.

**1.3.0** — **Pré-renderizar as miniaturas no build.** O shared renderer da 1.2.0 conserta
o estouro de contexto WebGL, não o carregamento: medido em produção, o elemento LCP era a
própria miniatura, com 39,9 s e 7.230 ms de render delay, e a geometria respondia por 57%
do peso da página. Documentado o padrão de dirigir o próprio template num Chromium
headless (Playwright) para obter imagem idêntica ao runtime, os flags de SwiftShader
obrigatórios sem GPU, a regra de uma miniatura por geometria, o `object-fit: contain` que
a proporção fixa exige, e a necessidade de manter o render dinâmico como fallback.

**1.2.0** — Shared renderer + captura JPEG para catálogos grandes (o padrão de um renderer por card estoura o limite de contextos WebGL). Caminho absoluto para a geometria, obrigatório com `cleanUrls`. Checagem de `r.ok` antes do `JSON.parse`. Cache de geometria por URL, já que peças diferentes compartilham malha. Validado em produção com 9 catálogos, o maior com 856 produtos.

**1.1.0** — Padrões de card, modal, curva Q-H em SVG e os dois layouts de catálogo.
