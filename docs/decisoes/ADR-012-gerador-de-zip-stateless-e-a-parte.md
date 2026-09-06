# ADR-012 — gerador de zip stateless e a parte

**Status:** Aceita (2026-09-06)

## Decisão

`servicos/gerador-zip` recebe um `.aq`/`.zip` e devolve o ZIP da bilds.com em stream. Não lê nem grava Mongo, não usa storage, não cria catálogo; upload e ZIP são apagados. Consome a biblioteca (parse, catálogo em memória, miniaturas, escrita do ZIP). O modo lote (`--all`) é a mesma CLI.

## Por quê

Palavras do usuário: 'lê um .aq e dá saída num zip, nada fica persistido, apenas as mesmas funções são consumidas'.

## Consequências

Um `.aq` grande leva o tempo do build; o serviço não tem fila.
