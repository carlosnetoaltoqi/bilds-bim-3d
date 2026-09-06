# Preview HTML estático — arquivado em 2026-09-06 (S8/F1, ADR-017)

Até 2026-09-06 o `scripts/build.py` gerava, além do ZIP da bilds.com, um **preview navegável**
(`output/preview/<slug>/index.html`) a partir de dois templates Jinja2 com Three.js inline
(`catalog-grid.html`, `series-rows.html`), um índice `catalogs.json` e uma landing feita à mão
(`index.html`). O preview era conveniência local: a bilds.com só consome o ZIP, e o web em React
(`web/`, página de catálogo) faz o mesmo papel com o mesmo viewer.

O que **ficou no produto**: a leitura do `.aq`, o catálogo, as miniaturas e o ZIP — tudo na
biblioteca `bim_pipeline`; o modo lote (`--all`, `--force`, `--input-dir`, `--skip-thumbs`,
`--allow-no-thumbs`) virou `python3 -m bim_pipeline.cli.zip_bilds --all`. O modo interativo com
`config.json` (perguntas sobre fabricante, título e layout) não foi levado: tudo é inferido do
`.aq` (`bim_pipeline.catalogo.inferencia`), como já era no `--all` e no serviço.

Os arquivos aqui **não são executados** por nada — servem de registro do padrão dos templates
(o "aperto de mão" de dois scripts, o importmap, o escape) que está descrito em
`docs/conhecimento/miniaturas.md` e nos registros de sessão.
