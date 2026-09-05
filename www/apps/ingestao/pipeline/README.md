# `pipeline/` — o pipeline Python do serviço de ingestão

Aqui mora o que lê o `.aq` e produz catálogo, geometria e miniaturas. É o **mesmo código**
que o pipeline estático (`scripts/build.py`, ZIP para a bilds.com) usa — o `build.py` importa
daqui. Movido de `scripts/` em 2026-09-05 (etapa E2 de `docs/arquitetura-www-servico-de-ingestao.md`)
para o serviço ser autocontido quando for isolado num repositório próprio.

| Arquivo | O quê |
|---|---|
| `read_aq.py` | abre o `.aq` (SQLite direto ou ZIP), extrai peças, grupos, propriedades, curvas, simbologias; `peek_metadata` |
| `oq3d.py` | o formato binário OQ3D → `{pos, col, idx}` em metros, Y-up |
| `dedup.py` | deduplicação de vértices com quantização float32 (~79 %) |
| `catalogo.py` | `.aq` → catálogo (produtos, séries) + um JSON de geometria por simbologia; `resumo_diag` |
| `inferencia.py` | fabricante, título, slug e layout a partir do `.aq` e do nome do arquivo (`auto_config`) |
| `miniaturas.py` | driver Python do `thumbs.mjs` (Node/Playwright): uma WebP por geometria |
| `thumbs.mjs` + `harness.html` | Chromium headless renderiza com o mesmo Three.js e câmera do viewer |
| `catalogo_de_aq.py` | **CLI** que o serviço executa: `.aq` → `--geo-dir` + `--saida` JSON (contrato na docstring) |
| `step_to_geo.py` · `ifc_to_geo.py` · `parse_ifc.py` | CAD → `{pos, col, idx}` (OpenCASCADE / parser IFC do projeto) |
| `aq_writer.py` + `schema-aq-607.sql` | **escrever** `.aq`: DDL completo do schema 607, constantes do AltoQi (sentinelas, IFC, aplicações), `EscritorAq` que grava texto em cp1252 (promovido do `eng-reversa/` em 2026-09-05, I4) |
| `oq3d_writer.py` | **escrever** OQ3D: malhas indexadas → blob que o `oq3d.py` (e o Builder) leem; cilindro/tubo paramétricos |
| `geo_to_aq.py` | `{pos, col, idx}` ou partes do editor → `.aq` com uma peça (usa os dois acima; nada de fora do serviço) |
| `processo.py` | `vigiar_stdin()`: o filho sai quando o pai morre |

Nenhum módulo importa nada de fora deste diretório (`tests/test_geo_to_aq.py` garante). Todos importam os irmãos com o próprio diretório no `sys.path` — quem usa faz
`sys.path.insert(0, '<este dir>')` e `import oq3d`, como `build.py`, `tests/conftest.py` e
`eng-reversa/tools/` fazem. O conhecimento sobre os formatos está em `docs/conhecimento/`
(`oq3d.md`, `read-aq.md`, `parse-ifc.md`, `pipeline-estatico.md`).

```bash
# ler uma biblioteca e gerar geometria + catálogo (sem miniaturas)
python3 www/apps/ingestao/pipeline/catalogo_de_aq.py input/Dancor/pecas.aq --geo-dir /tmp/geo --saida /tmp/cat.json
# com miniaturas (precisa de pnpm install na raiz e Chromium do Playwright)
python3 www/apps/ingestao/pipeline/catalogo_de_aq.py input/Dancor/pecas.aq --geo-dir /tmp/geo --saida /tmp/cat.json --thumbs-dir /tmp/thumbs
```
