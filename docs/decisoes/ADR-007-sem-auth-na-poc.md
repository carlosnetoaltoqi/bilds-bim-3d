# ADR-007 — sem auth na poc

**Status:** Aceita (2026-09-05, A7; mantida)

## Decisão

Sem login, JWT, guardas de acesso, middleware do Next ou rotas-proxy. O web fala direto com os serviços (CORS por `WEB_ORIGIN`). Empresa é agrupador de catálogos escolhido por `customUrl`.

## Por quê

POC enquanto viver neste repositório.

## Consequências

Qualquer incremento de produção precisa da lista de `docs/historico/estudos/` ('o que a POC não implementou').
