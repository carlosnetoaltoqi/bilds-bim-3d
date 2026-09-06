# Contratos biblioteca ↔ serviços (ADR-015)

| Schema | Quem emite | Quem lê |
|---|---|---|
| `catalogo` | `cli.catalogo_de_aq`, `cli.plugin_catalogo_web importar` (`--saida`) | criador de catálogos (publicação) |
| `geometria` | `cli.step_iges`, `cli.ifc`, geometrias de `--geo-dir` | conversores, criador, editor, viewer |
| `manifesto-catalogo-aq` | criador de catálogos (do banco) | `cli.catalogo_para_aq` |
| `resumo-miniaturas` | `miniaturas/thumbs.mjs` (uma linha por geometria) | criador de catálogos |
| `info-plugin` | `cli.plugin_catalogo_web inspecionar` | conversores, criador |

A biblioteca prova em teste que emite conforme (`tests/test_contratos.py`, com `jsonschema`);
`@bim/base` valida o que lê (`validarContrato`, com `ajv`). Uma mudança de contrato falha nos dois lados.
