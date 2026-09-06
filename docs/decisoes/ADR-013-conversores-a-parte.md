# ADR-013 — conversores a parte

**Status:** Aceita (2026-09-06)

## Decisão

`servicos/conversores` expõe tesselação (STEP/IGES/IFC → geometria), geração de `.aq` de uma peça e inspeção de DLL de plugin web. Stateless.

## Por quê

Tesselação, geração de `.aq` de uma peça e inspeção de DLL não dependem de ingestão nem de Mongo; num serviço com dados ficariam atrás de um guarda de banco sem precisar dele.

## Consequências

O criador roda a mesma CLI de inspeção localmente ao receber um import de plugin — mesma função, dois consumidores, zero cópia.
