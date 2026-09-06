# ADR-015 — contratos em json schema

**Status:** Aceita (2026-09-06)

## Decisão

Os JSONs que cruzam a fronteira biblioteca ↔ serviço (catálogo, geometria, manifesto de catálogo → `.aq`, resumo de miniaturas, informação de plugin) têm JSON Schema em `biblioteca/bim_pipeline/contratos/` (a biblioteca define o que emite; assim um contexto portado leva o contrato junto com a biblioteca). A biblioteca prova em teste que emite conforme o schema; `pacotes/base` valida o que lê.

## Por quê

Até aqui os contratos eram interfaces TypeScript espelhando docstrings Python, validadas só por `JSON.parse`.

## Consequências

Mais um artefato a manter; em troca, uma mudança de contrato falha nos dois lados.
