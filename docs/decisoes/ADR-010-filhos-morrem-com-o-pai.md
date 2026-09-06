# ADR-010 — filhos morrem com o pai

**Status:** Aceita (2026-09-05)

## Decisão

Todo processo filho (Python e `thumbs.mjs`) recebe `stdin` em pipe e sai ao ver EOF (`--sair-com-stdin` / `sairComStdin`). Exit 2 significa 'o pai morreu'.

## Por quê

Um `kill -9` no serviço não pode deixar Python nem Chromium órfãos; o EOF do `stdin` é o sinal que funciona sem IPC.

## Consequências

Toda CLI da biblioteca precisa aceitar a flag.
