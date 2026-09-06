# ADR-006 — miniatura por geometria regerada pelo criador

**Status:** Aceita (2026-09-05)

## Decisão

A miniatura é do produto (`thumbs/<importId>/<productId>.webp`), mas produtos que compartilham geometria compartilham o render: o criador renderiza por geometria e grava a chave em cada produto. Após edição, o editor pede a regeneração ao criador (`POST /miniaturas/regerar`).

## Por quê

Uma renderização por geometria; só o criador tem Chromium.

## Consequências

O editor depende da disponibilidade do criador para a miniatura nova (falha vira `thumbErro`, não erro do `PUT`).
