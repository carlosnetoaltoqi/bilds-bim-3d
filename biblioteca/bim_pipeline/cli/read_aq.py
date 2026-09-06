"""CLI `python -m bim_pipeline.cli.read_aq` — o `main()` de `bim_pipeline.aq.read_aq`."""
import runpy

runpy.run_module('bim_pipeline.aq.read_aq', run_name='__main__')
