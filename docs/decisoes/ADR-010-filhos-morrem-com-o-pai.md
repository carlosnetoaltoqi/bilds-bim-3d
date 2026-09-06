# ADR-010 — filhos morrem com o pai

**Status:** Aceita (2026-09-05, A10; mantida)

## Decisão

Todo processo filho (Python e `thumbs.mjs`) recebe `stdin` em pipe e sai ao ver EOF (`--sair-com-stdin` / `sairComStdin`). Exit 2 significa 'o pai morreu'.

## Por quê

Substitui o `disconnect` do IPC sem `fork`; um `kill -9` no serviço não deixa Python nem Chromium órfãos.

## Consequências

Toda CLI da biblioteca precisa aceitar a flag.
