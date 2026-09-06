import { Injectable } from '@nestjs/common';
import { Biblioteca, bibliotecaDir } from '@bim/base';

/**
 * PipelineService — a `Biblioteca` de @bim/base (o cliente tipado da biblioteca Python) como
 * provider do Nest. Os métodos e os tipos moram na base desde a S8/F3; aqui só o que o Nest
 * precisa para injetar.
 */
@Injectable()
export class PipelineService extends Biblioteca {}

export type {
  AqInfo, AqParte, LeadDownload, ManifestoCatalogoAq, PluginInfo, ProdutoPipeline, ResultadoCatalogo,
  ResumoMiniaturas, StepGeo,
} from '@bim/base';
export { formatoDe } from '@bim/base';

/** Compat: quem imprime onde a biblioteca está (health, main). */
export const pipelineDir = bibliotecaDir;
