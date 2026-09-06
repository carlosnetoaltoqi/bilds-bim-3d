# ADR-011 — biblioteca comum stateless

**Status:** Aceita (2026-09-06)

## Decisão

`bim_pipeline` é a única implementação de: leitura e escrita de `.aq`/OQ3D, contrato de geometria e conversões de eixos, dedup, slug, inferência, montagem do catálogo, miniaturas, escrita do ZIP e conversores. Não conhece Mongo, HTTP, portas nem caminhos do repositório. Toda função é consumida por mais de um contexto (o criador e o gerador de ZIP usam as mesmas funções de catálogo e miniatura).

## Por quê

Toda função que dois contextos precisam (catálogo, miniaturas, escrita do ZIP) tem de existir uma vez só; uma cópia por contexto diverge.

## Consequências

Teste de fronteira: nenhum `import` de fora do pacote; grep de `pymongo`/`http` vazio.
