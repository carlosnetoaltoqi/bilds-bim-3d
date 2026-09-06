# ADR-003 — casca nest fina python como processo filho

**Status:** Aceita (2026-09-05; confirmada em 2026-09-06)

## Decisão

Os serviços são cascas NestJS finas (upload, fila, status, recuperação no boot, gravação no Mongo) que rodam as CLIs da biblioteca Python como processos filhos. O Python continua stateless e não grava no banco.

## Por quê

Decisão do usuário entre 'serviço Python grava' e 'Python = biblioteca, Nest grava'. A casca Nest concentra fila, recuperação no boot, validação e nomes UTF-8; o Python fica portável.

## Consequências

Os contratos entre Python e TypeScript passam por JSON em arquivo (ADR-015 os torna verificáveis).
