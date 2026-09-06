# ADR-009 — estudos arquivados ferramentas promovidas

**Status:** Aceita (2026-09-06)

## Decisão

Estudos, planos superados e registros de sessão ficam em `docs/historico/`, com nota apontando para onde o conhecimento foi. Ferramentas genéricas (anatomia do OQ3D, referência de enums de um `.aq`, validador de `.aq`, ida e volta do OQ3D, formas paramétricas) fazem parte da biblioteca. Geradores específicos de um fabricante ficam como exemplos arquivados, fora da suíte.

## Por quê

O conhecimento técnico dos estudos foi promovido para `docs/conhecimento/`; a suíte não pode depender de um diretório de estudo.

## Consequências

O histórico mantém nomes de fabricantes — é registro, não conhecimento, e não é carregado ao iniciar uma sessão.
