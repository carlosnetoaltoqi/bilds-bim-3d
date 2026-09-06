"""CLI `python -m bim_pipeline.cli.ifc` — o `main()` de `bim_pipeline.conversores.ifc`."""
import runpy

runpy.run_module('bim_pipeline.conversores.ifc', run_name='__main__')
