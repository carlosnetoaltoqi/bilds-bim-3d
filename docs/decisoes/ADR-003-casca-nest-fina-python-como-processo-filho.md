# ADR-003 — casca nest fina python como processo filho

**Status:** Aceita (2026-09-05, A3; confirmada pelo usuário em 2026-09-06)

## Decisão

Os serviços são cascas NestJS finas (upload, fila, status, recuperação no boot, gravação no Mongo) que rodam as CLIs da biblioteca Python como processos filhos. O Python continua stateless e não grava no banco.

## Por quê

Confirmado explicitamente pelo usuário em 2026-09-06 ao escolher entre 'serviço Python grava' e 'Python = biblioteca, Nest grava'. Reaproveita a infraestrutura endurecida em S7.11–S7.13 (fila, recuperação, validação, nome UTF-8).

## Consequências

Os contratos entre Python e TypeScript passam por JSON em arquivo (ADR-015 os torna verificáveis).
