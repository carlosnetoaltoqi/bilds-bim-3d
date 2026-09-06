# `bim_pipeline` — a biblioteca comum

Pacote Python **stateless** que sabe tudo o que este projeto sabe sobre bibliotecas BIM do
AltoQi Builder e sobre a geometria que sai delas: ler e escrever `.aq`/OQ3D, montar um catálogo,
gerar miniaturas no Chromium, escrever o ZIP da bilds.com, converter STEP/IGES/IFC e ler catálogos
de plugins web. Não conhece Mongo, HTTP, portas nem caminhos do repositório: **arquivo entra,
arquivo ou JSON sai** (ADR-011). Todo contexto do sistema — criador de catálogos, gerador de ZIP,
editor de peças, conversores — consome as mesmas funções daqui, por CLI (ADR-003, ADR-004).

```bash
pip install -e biblioteca            # o pacote (numpy)
pip install -e 'biblioteca[cad,dev]' # + OpenCASCADE, ifcopenshell, pypdf; + pytest (numpy e olefile vêm sempre)
(cd biblioteca/bim_pipeline/miniaturas && pnpm install)   # Playwright (Chromium) + three, só para miniaturas
```

## Mapa

| Subpacote | O quê |
|---|---|
| `aq/` | `read_aq` (abre `.aq` SQLite ou ZIP, decodifica **cp1252**, extrai peças/grupos/propriedades/curvas/simbologias), `oq3d` (**leitor** tolerante do blob OQ3D → `{pos, col, idx}`), `aq_writer` + `schema-aq-607.sql` (**escrever** `.aq`: DDL, enums do AltoQi, `EscritorAq` em cp1252, `classificar_grupo`), `oq3d_writer` (**escrever** OQ3D), `formas_parametricas` (forma representativa por parâmetro) |
| `geometria/` | o contrato `{pos, col, idx}` (metros, Y-up): `eixos` (as conversões Z-up ↔ viewer, num lugar só), `dedup` (quantização float32 pos+cor, vetorizado), `malhas` (geometria do viewer → malhas por cor para o OQ3D), `perfis` (seções 2D extrudadas — I, U, L, tubos, caixa, chapa trapezoidal — para formas representativas de perfis; sólidos fechados) |
| `catalogo/` | `catalogo.build_catalog_from_aq` (o miolo: `.aq` → produtos, séries, filtros, uma geometria por simbologia), `inferencia` (fabricante/título/slug/layout do `.aq` e do caminho, sem perguntas), `montar_resultado` (o JSON do contrato), `fontes/plugin_catalogo_web` (plugin de CAD que é casca de um catálogo web → o mesmo catálogo), `fontes/familias_revit` (famílias `.rfa` soltas, em pasta ou `.zip` → o mesmo catálogo: tipos do PartAtom/type catalog, geometria irmã IFC/STEP/IGES ou forma representativa) |
| `conversores/` | `step_iges` (OpenCASCADE; IGES de faces soltas costurado e orientado pelo volume assinado), `ifc` + `parse_ifc` (caminho exato puro-Python e caminho rápido via ifcopenshell), `rfa_partatom` (o que se lê de uma família Revit sem o Revit: `BasicFileInfo`, `PartAtom`, preview), `type_catalog` (o `.txt` de tipos de uma família Revit), `aps` (projeto `.rvt` → IFC pela Autodesk Platform Services, com cache), `ifc_elementos` (IFC de projeto → elementos com geometria local, família/tipo, psets) |
| `miniaturas/` | `render.build_thumbs` + `thumbs.mjs` + `harness.html`: uma WebP por geometria, no Chromium, com a **mesma cena do viewer**; `package.json` próprio (Playwright + three) — ninguém fora daqui sabe onde está o `three` |
| `saida/` | `zip_bilds` (o **único** escritor do ZIP da bilds.com; `gerar_zip` faz `.aq` → ZIP num diretório temporário), `geo_to_aq` (uma peça → `.aq`), `catalogo_to_aq` (catálogo salvo → `.aq` novo com N peças) |
| `processo.py` | `vigiar_stdin()`: o processo sai com 2 quando o pai fecha o `stdin` (ADR-010) |
| `cli/` | **é por aqui que os serviços entram**: `python -m bim_pipeline.cli.<nome>` |

### CLIs

| `python -m bim_pipeline.cli.…` | Faz | Quem chama |
|---|---|---|
| `catalogo_de_aq <aq> --geo-dir D --saida X.json [--nome-original] [--thumbs-dir] [--sair-com-stdin]` | `.aq`/`.zip` → geometrias em `D` + catálogo JSON (`contratos/catalogo`) | criador de catálogos |
| `zip_bilds <aq> --saida X.zip [--skip-thumbs \| --allow-no-thumbs] [--sair-com-stdin]` · `zip_bilds --all [--input-dir] [--output-dir] [--force] [--layout]` | `.aq` → ZIP da bilds.com; lote espelhando subpastas | gerador de ZIP; operador |
| `step_iges <cad> <saida.json> [--deflexao] [--info]` · `ifc <ifc> <saida.json>` | CAD → `{pos, col, idx, partes, …}` | conversores; criador (peça CAD) |
| `gerar_aq <geo.json> <saida.aq> [--fabricante …]` | geometria/partes → `.aq` de uma peça | conversores; editor |
| `catalogo_para_aq <manifesto.json> <saida.aq>` | catálogo salvo → `.aq` inteiro | criador de catálogos |
| `plugin_catalogo_web inspecionar <dll>` · `… importar --host --categoria --lead --downloads --geo-dir --saida` | plugin web → host/categorias; categoria → downloads + tesselação → catálogo | conversores (inspecionar); criador (importar) |
| `familias_revit inspecionar <rfa\|rvt\|pasta\|zip>` · `… importar <entrada> --geo-dir --saida [--titulo] [--fabricante] [--comprimento-mm] [--deflexao] [--aps\|--aps-credenciais J] [--aps-cache D] [--sair-com-stdin]` | famílias Revit → famílias/tipos/categorias/projetos (`contratos/info-familias-revit`); → geometrias (irmã, representativa, ou IFC do projeto via APS) + catálogo | criador de catálogos |
| `aps <projeto.rvt> <saida.ifc> [--credenciais J] [--cache D]` | um `.rvt` → IFC pela APS Model Derivative (credenciais também por `APS_CLIENT_ID`/`APS_CLIENT_SECRET`) | operador |
| `read_aq`, `dedup`, `parse_ifc`, `rfa_partatom` | utilitários dos módulos homônimos | operador |
| `ferramentas.validar_aq <aq> [--tubo-cm] [--max-conexao-cm]` · `ferramentas.aq_referencia <aq>` · `ferramentas.oq3d_anatomy <aq> <sid>` · `ferramentas.oq3d_roundtrip [--aq …]` | validar um `.aq` gerado com os leitores daqui; extrair enums de um `.aq` real; dissecar um blob byte a byte; provar o escritor OQ3D contra o leitor | operador; suíte |

Toda CLI que um serviço roda aceita `--sair-com-stdin`; progresso vai para **stderr**, resultado
para arquivo ou stdout; exit 0 ok, 1 erro, 2 "o pai morreu".

## Regras

- Nenhum módulo importa nada de fora de `bim_pipeline` (`tests/arquitetura/test_biblioteca_isolada.py` garante) e
  nenhum conhece Mongo, HTTP ou caminhos do repositório.
- Uma implementação por coisa: um `slugify`, um `dedup`, um lugar para as conversões de eixos, um
  escritor de ZIP, um produtor do dict de catálogo. Duplicar aqui é regressão.
- Sem fabricantes, arquivos ou caminhos da POC em código, docstring ou comentário (ADR-016):
  exemplos são neutros e censos viram proporções.
- O conhecimento sobre os formatos está em `docs/conhecimento/` — os módulos apontam para lá; os
  docstrings dizem só o que o código faz.
- Testes em `tests/` (raiz): `python3 -m pytest -m "not thumbs"` roda tudo sem Chromium.
