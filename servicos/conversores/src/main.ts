import 'reflect-metadata';
import * as path from 'node:path';
import { carregarEnv, iniciarServico, bibliotecaDir } from '@bim/base';

carregarEnv(path.resolve(__dirname, '../../../.env'));

import { AppModule } from './app.module';

/**
 * Conversores (docs/arquitetura.md, ADR-013): tesselar CAD, gerar `.aq` de uma peça, inspecionar a
 * DLL de um plugin de CAD. Síncronos, stateless. Porta `CONVERSORES_PORT` (4300). `X-Aq-Resumo` vai
 * num header, então é exposto no CORS.
 */
iniciarServico(AppModule, {
  nome: 'conversores', envPorta: 'CONVERSORES_PORT', portaPadrao: 4300, exposedHeaders: ['X-Aq-Resumo'],
  aoSubir: () => console.log(`biblioteca em ${bibliotecaDir()}`),
});
