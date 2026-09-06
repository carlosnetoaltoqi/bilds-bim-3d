# ADR-013 — conversores a parte

**Status:** Aceita (2026-09-06)

## Decisão

`servicos/conversores` expõe tesselação (STEP/IGES/IFC → geometria), geração de `.aq` de uma peça e inspeção de DLL de plugin web. Stateless.

## Por quê

Eram rotas do serviço de ingestão sem nenhuma relação com ingestão; ficavam atrás do guarda de Mongo sem precisar dele.

## Consequências

O criador roda a mesma CLI de inspeção localmente ao receber um import de plugin — mesma função, dois consumidores, zero cópia.
