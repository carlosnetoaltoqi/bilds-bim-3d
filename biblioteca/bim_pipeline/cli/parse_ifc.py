"""CLI `python -m bim_pipeline.cli.parse_ifc` — o `main()` de `bim_pipeline.conversores.parse_ifc`."""
import runpy

runpy.run_module('bim_pipeline.conversores.parse_ifc', run_name='__main__')
