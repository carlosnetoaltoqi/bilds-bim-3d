"""CLI `python -m bim_pipeline.cli.gerar_aq` — o `main()` de `bim_pipeline.saida.geo_to_aq`."""
import runpy

runpy.run_module('bim_pipeline.saida.geo_to_aq', run_name='__main__')
