# Reengenharia em contextos desacoplados — fases F0–F6 (2026-09-06)

Tabela de fases retirada de `docs/arquitetura.md` §6 em 2026-09-06, quando todas fecharam. O plano completo
está em `docs/historico/planos/plans/` e a arquitetura anterior em `arquitetura-www-servico-de-ingestao.md`.
Cada fase tem um registro em `../sessoes/S8.<n>-*.md`.

| Fase | Entregável | Estado |
|---|---|---|
| **F0** | Este documento; `docs/decisoes/` (ADR-001 a ADR-017); a arquitetura anterior arquivada em `docs/historico/planos/` | ✅ 2026-09-06 |
| **F1** | Biblioteca `bim_pipeline` como pacote instalável, sem duplicações, com o modo lote do antigo `build.py`, ferramentas genéricas do estudo promovidas, fixtures por papel; preview estático sai; sem fabricantes em código | ✅ 2026-09-06 (S8.1) |
| **F2** | Workspace pnpm na raiz; `pacotes/base` e `pacotes/dominio` compilados com project references (`pnpm -r start` funciona); contratos em JSON Schema validados nos dois lados | ✅ 2026-09-06 (S8.2) |
| **F3** | `servicos/gerador-zip` e `servicos/conversores` (stateless); web com um cliente por serviço para eles; cliente tipado da biblioteca em `@bim/base` | ✅ 2026-09-06 (S8.3) |
| **F4** | `servicos/criador-de-catalogos` (importação/publicação/miniaturas divididas), `servicos/catalogo-api` (só leitura), `servicos/editor-de-pecas`; `web/` na raiz com um cliente por serviço; `www/` deixa de existir | ✅ 2026-09-06 (S8.4) |
| **F5** | `tests/{biblioteca,servicos,arquitetura}`; as sete regras como testes (+ termos da POC, contratos, dependências); CI por camada; `README.md`; `docs/aceitacao.md`; código e testes sem termos da POC | ✅ 2026-09-06 (S8.5) |
| **F6** | `docs/conhecimento/` reescrito por formato/algoritmo sem empresas (16 documentos); skills como how-to apontando para lá (`referencias/`); `docs/historico/{sessoes,estudos,planos}`; `docs/integracoes/`; `CLAUDE.md`, `CONCEPTS.md`, `README.md`; a guarda de termos cobre docs e skills | ✅ 2026-09-06 (S8.6) |

Regras de execução: um commit por item; cada fase termina com `python3 -m pytest -m "not thumbs"`
e `pnpm -r build` verdes; documentação do que mudou no mesmo commit; registro da sessão em
`docs/historico/sessoes/`.
