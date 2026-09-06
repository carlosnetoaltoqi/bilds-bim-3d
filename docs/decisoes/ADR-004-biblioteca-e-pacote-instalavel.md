# ADR-004 — biblioteca e pacote instalavel

**Status:** Aceita (2026-09-06)

## Decisão

O código Python mora em `biblioteca/` como pacote `bim_pipeline` instalável (`pip install -e biblioteca[cad,dev]`). Ninguém entra nele por `sys.path.insert`; os serviços o alcançam por `python -m bim_pipeline.cli.<nome>` através de `pacotes/base`.

## Por quê

Um pacote é a unidade que qualquer contexto pode levar consigo; entrar por caminho do repositório amarrava a biblioteca a um serviço e a suíte a caminhos.

## Consequências

Exige `pip install -e` no bootstrap e no CI.
