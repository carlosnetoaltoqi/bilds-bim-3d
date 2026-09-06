# ADR-001 — um deployable por contexto

**Status:** Aceita (2026-09-06)

## Decisão

Cada contexto de negócio — criador de catálogos, API de catálogo, editor de peças, gerador de ZIP, conversores — é um serviço com `main.ts`, porta, `.env` e README próprios em `servicos/<contexto>/`. Na POC todos sobem na mesma máquina com um comando; falam entre si por HTTP.

## Por quê

Cada parte deve poder ser portada para outro sistema levando só o que é sua. A separação em deployables é o que torna isso verificável: `docs/arquitetura.md` §4 lista o que cada contexto leva.

## Consequências

Mais processos para subir (seis); a fronteira entre criador, catalogo-api e editor é só por HTTP e por dados compartilhados (ADR-004).
