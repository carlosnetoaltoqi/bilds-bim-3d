# ADR-016 — sem empresas fora do historico

**Status:** Aceita (2026-09-06)

## Decisão

Nomes de fabricante, domínios, arquivos e caminhos da POC não aparecem em código, contratos, conhecimento nem skills. Fixtures de teste são referenciadas por papel (`aq_pequena`, `aq_grande`, `step_peca`…) num arquivo local gitignored. Censos de uma biblioteca específica viram proporções, e a proveniência aponta para o registro da sessão em `docs/historico/`.

## Por quê

Pedido do usuário: o conhecimento é sobre formatos, algoritmos e padrões; empresas e arquivos são efêmeros à POC.

## Consequências

Teste `tests/arquitetura/test_sem_empresas.py` com a lista de termos; a evidência numérica fica só no histórico.
