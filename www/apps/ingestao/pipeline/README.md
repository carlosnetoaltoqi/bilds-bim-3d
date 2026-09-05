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
| `geo_to_aq.py` | `{pos, col, idx}` → `.aq` (usa `eng-reversa/tools/`, único vínculo com fora do serviço) |
| `processo.py` | `vigiar_stdin()`: o filho sai quando o pai morre |

Todos os módulos importam os irmãos com o próprio diretório no `sys.path` — quem usa faz
`sys.path.insert(0, '<este dir>')` e `import oq3d`, como `build.py`, `tests/conftest.py` e
`eng-reversa/tools/` fazem. O conhecimento sobre os formatos está em `docs/conhecimento/`
(`oq3d.md`, `read-aq.md`, `parse-ifc.md`, `pipeline-estatico.md`).

```bash
# ler uma biblioteca e gerar geometria + catálogo (sem miniaturas)
python3 www/apps/ingestao/pipeline/catalogo_de_aq.py input/Dancor/pecas.aq --geo-dir /tmp/geo --saida /tmp/cat.json
# com miniaturas (precisa de pnpm install na raiz e Chromium do Playwright)
python3 www/apps/ingestao/pipeline/catalogo_de_aq.py input/Dancor/pecas.aq --geo-dir /tmp/geo --saida /tmp/cat.json --thumbs-dir /tmp/thumbs
```
