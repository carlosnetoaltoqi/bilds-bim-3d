import 'reflect-metadata';
import * as path from 'node:path';
import { carregarEnv, iniciarServico, bibliotecaDir } from '@bim/base';

// .env da raiz do repositório (src → criador-de-catalogos → servicos → raiz)
carregarEnv(path.resolve(__dirname, '../../../.env'));

import { storagePath, storagePathDefinido } from '@bim/dominio';
import { AppModule } from './app.module';

/**
 * Criador de catálogos (docs/arquitetura.md §2; ADR-003, ADR-005, ADR-006). Recebe uploads,
 * enfileira, roda a biblioteca Python e o Chromium como processos filhos, grava no Mongo e no
 * storage. Não serve páginas nem geometria — isso é da API de catálogo. Porta `CRIADOR_PORT` (4100).
 */
iniciarServico(AppModule, {
  nome: 'criador-de-catalogos', envPorta: 'CRIADOR_PORT', portaPadrao: 4100, exposedHeaders: ['X-Aq-Resumo'],
  aoSubir: () => {
    console.log(`biblioteca em ${bibliotecaDir()}`);
    console.log(`storage em ${storagePath()}${storagePathDefinido() ? '' : '  (STORAGE_PATH não definido — usando o padrão; veja .env.example)'}`);
  },
});
