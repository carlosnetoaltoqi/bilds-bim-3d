import 'reflect-metadata';
import * as path from 'node:path';
import { carregarEnv, iniciarServico } from '@bim/base';

carregarEnv(path.resolve(__dirname, '../../../.env'));

import { storagePath, storagePathDefinido } from '@bim/dominio';
import { AppModule } from './app.module';

/**
 * API de catálogo — leitura (docs/arquitetura.md §2): empresas, catálogos, produtos, geometria e
 * miniaturas, remoção em cascata. Sem Python nem Chromium; a edição é do editor-de-pecas (:4400).
 * Porta `CATALOGO_PORT` (4000).
 */
iniciarServico(AppModule, {
  nome: 'catalogo-api', envPorta: 'CATALOGO_PORT', portaPadrao: 4000,
  aoSubir: () => console.log(`storage em ${storagePath()}${storagePathDefinido() ? '' : '  (STORAGE_PATH não definido — usando o padrão; veja .env.example)'}`),
});
