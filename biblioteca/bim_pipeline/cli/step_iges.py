"""CLI `python -m bim_pipeline.cli.step_iges` — o `main()` de `bim_pipeline.conversores.step_iges`."""
import runpy

runpy.run_module('bim_pipeline.conversores.step_iges', run_name='__main__')
