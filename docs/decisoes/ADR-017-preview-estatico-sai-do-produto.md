# ADR-017 — preview estatico sai do produto

**Status:** Aceita (2026-09-06)

## Decisão

O preview HTML estático (templates Jinja, `templates/vendor`, `output/preview`, `catalogs.json`) deixa o produto e vai para o histórico. O web em React é a única página de catálogo; o ZIP é gerado pela CLI/serviço.

## Por quê

O web em React e o preview HTML eram duas implementações do mesmo viewer, com cópias de `buildScene`. Só a bilds.com consome o ZIP; o preview era conveniência local.

## Consequências

Quem quiser ver um catálogo localmente sobe o web e importa pelo criador.
