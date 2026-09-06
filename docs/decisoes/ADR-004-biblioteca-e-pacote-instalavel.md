# ADR-004 — biblioteca e pacote instalavel

**Status:** Aceita (2026-09-06; substitui A4)

## Decisão

O código Python mora em `biblioteca/` como pacote `bim_pipeline` instalável (`pip install -e biblioteca[cad,dev]`). Ninguém entra nele por `sys.path.insert`; os serviços o alcançam por `python -m bim_pipeline.cli.<nome>` através de `pacotes/base`.

## Por quê

A A4 punha o pipeline dentro do serviço de ingestão e fazia o `build.py` importá-lo de lá por caminho; isso amarrava a biblioteca a um serviço e a suíte a caminhos do repositório. Um pacote é a unidade que qualquer contexto pode levar consigo.

## Consequências

Exige `pip install -e` no bootstrap e no CI.
