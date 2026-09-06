import 'reflect-metadata';
import * as path from 'node:path';
import { carregarEnv, iniciarServico, bibliotecaDir } from '@bim/base';

// .env da raiz do repositório (src → gerador-zip → servicos → raiz); fora do repo, as variáveis vêm do ambiente
carregarEnv(path.resolve(__dirname, '../../../.env'));

import { AppModule } from './app.module';

/**
 * Gerador de ZIP (docs/arquitetura.md, ADR-012): `.aq`/`.zip` → ZIP do formato bilds.com, em stream.
 * Não lê nem grava Mongo, não usa storage; upload e ZIP são temporários. Porta `ZIP_PORT` (4200).
 */
iniciarServico(AppModule, {
  nome: 'gerador-zip', envPorta: 'ZIP_PORT', portaPadrao: 4200,
  aoSubir: () => console.log(`biblioteca em ${bibliotecaDir()}`),
});
