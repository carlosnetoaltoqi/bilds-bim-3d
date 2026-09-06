# ADR-005 — copy on write na geometria compartilhada

**Status:** Aceita (2026-09-05)

## Decisão

Uma geometria por simbologia, compartilhada entre produtos. Na primeira edição de um produto que compartilha geometria, o serviço grava um arquivo só dele (`geo/<importId>/<productId>.json`) e guarda a chave compartilhada em `geoKeyCompartilhada`; restaurar desfaz. Geometria exclusiva ganha `.orig.json` na primeira escrita.

## Por quê

Editar um produto não pode mudar os irmãos; apagar um produto não pode apagar a geometria dos outros.

## Consequências

O editor precisa contar quantos produtos usam a geometria antes de gravar; a remoção em cascata precisa saber se é o último usuário.
