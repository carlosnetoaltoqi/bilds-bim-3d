"""CLI `python -m bim_pipeline.cli.plugin_catalogo_web` — o `main()` de `bim_pipeline.catalogo.fontes.plugin_catalogo_web`."""
import runpy

runpy.run_module('bim_pipeline.catalogo.fontes.plugin_catalogo_web', run_name='__main__')
