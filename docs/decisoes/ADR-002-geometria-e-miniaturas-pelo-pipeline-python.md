# ADR-002 — geometria e miniaturas pelo pipeline python

**Status:** Aceita (2026-09-05, A2; mantida)

## Decisão

O parse do `.aq`, a extração de geometria OQ3D, a dedup, o catálogo e as miniaturas (Chromium via Playwright, `thumbs.mjs` + `harness.html`) são feitos pelo código Python da biblioteca. Não existe parser `.aq`/OQ3D em TypeScript.

## Por quê

É o caminho provado em produção no ZIP da bilds.com. O port TypeScript não se mostrou eficiente na geração de miniaturas e foi removido em 2026-09-05.

## Consequências

Todo serviço que precisa de parse roda um processo filho Python (ADR-003).
