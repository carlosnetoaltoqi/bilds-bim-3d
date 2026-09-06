import 'reflect-metadata';
import * as path from 'node:path';
import { carregarEnv, iniciarServico } from '@bim/base';

carregarEnv(path.resolve(__dirname, '../../../.env'));

import { storagePath, storagePathDefinido } from '@bim/dominio';
import { AppModule } from './app.module';

/**
 * Editor de peças (docs/arquitetura.md §2, ADR-014): as ESCRITAS de edição — informações do produto
 * (`PATCH /produtos/:id`, com `infoOriginal`), geometria (`PUT /geometrias/:id`, copy-on-write e
 * `.orig`; `restaurar`; `original`). Pede a miniatura nova ao criador de catálogos (ADR-006). A
 * leitura de catálogo é da API de catálogo (:4000). Porta `EDITOR_PORT` (4400).
 */
iniciarServico(AppModule, {
  nome: 'editor-de-pecas', envPorta: 'EDITOR_PORT', portaPadrao: 4400,
  aoSubir: () => console.log(`storage em ${storagePath()}${storagePathDefinido() ? '' : '  (STORAGE_PATH não definido — usando o padrão; veja .env.example)'}`),
});
