"""CLI `python -m bim_pipeline.cli.aps` — o `main()` de `bim_pipeline.conversores.aps` (.rvt → IFC pela Autodesk Platform Services)."""
import runpy

runpy.run_module('bim_pipeline.conversores.aps', run_name='__main__')
