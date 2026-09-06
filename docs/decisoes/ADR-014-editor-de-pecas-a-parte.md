# ADR-014 — editor de pecas a parte

**Status:** Aceita (2026-09-06)

## Decisão

`servicos/editor-de-pecas` é o dono das escritas de edição: `PATCH /produtos/:id`, `PUT /geometrias/:id` (copy-on-write), restaurar, original. A API de catálogo fica só de leitura, empresas e remoção.

## Por quê

O editor é um dos contextos nomeados pelo usuário e o único com lógica de edição; misturado na API de leitura não é portável.

## Consequências

Editor e catalogo-api escrevem nas mesmas coleções — acoplamento aceito da POC, registrado em `docs/arquitetura.md` §5.
