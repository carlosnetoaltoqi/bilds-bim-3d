import 'reflect-metadata';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Carrega www/.env antes de qualquer módulo NestJS (src → ingestao → apps → www)
dotenv.config({ path: path.resolve(__dirname, '../../../.env') });

import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { storagePath, storagePathDefinido } from '@bim/dominio';
import { criarValidationPipe } from '@bim/base';
import { AppModule } from './app.module';
import { pipelineDir } from './pipeline/pipeline.service';

/**
 * Serviço de ingestão (docs/arquitetura-www-servico-de-ingestao.md, A1–A3).
 *
 * Recebe uploads, enfileira, roda o pipeline Python e o Chromium como processos filhos,
 * grava no Mongo e no storage. Não serve páginas nem geometria — isso é da API de
 * catálogo (apps/api). Porta `INGESTAO_PORT` (padrão 4100).
 */

// `POST /exportar/aq` recebe as partes do editor como JSON; uma peça grande passa de 10 MB.
const JSON_BODY_LIMIT = process.env.JSON_BODY_LIMIT ?? '300mb';
const PORT = Number(process.env.INGESTAO_PORT ?? 4100);
if (!Number.isInteger(PORT) || PORT <= 0 || PORT > 65535) {
  throw new Error(`INGESTAO_PORT inválida: ${JSON.stringify(process.env.INGESTAO_PORT)} — use um inteiro entre 1 e 65535`);
}

async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    logger: ['error', 'warn', 'log', 'verbose', 'debug'],
    bodyParser: false,
  });
  app.useBodyParser('json', { limit: JSON_BODY_LIMIT });
  app.useBodyParser('urlencoded', { extended: true, limit: JSON_BODY_LIMIT });
  app.useGlobalPipes(criarValidationPipe());

  app.use((req: any, res: any, next: any) => {
    const t = Date.now();
    const size = req.headers['content-length'] ? `${(+req.headers['content-length'] / 1024 / 1024).toFixed(1)} MB` : '-';
    res.on('finish', () => {
      if (req.url !== '/health') {
        console.log(`[http] ${req.method} ${req.url} body=${size} → ${res.statusCode} (${Date.now() - t}ms)`);
      }
    });
    next();
  });

  app.enableCors({
    origin: process.env.WEB_ORIGIN ?? 'http://localhost:3000',
    credentials: true,
    // o download do .aq devolve o resumo num header; sem expor, o browser não o lê
    exposedHeaders: ['X-Aq-Resumo', 'Content-Disposition'],
  });
  await app.listen(PORT);
  // Conversão de CAD grande pode levar minutos e um upload de 600 MB também; o Node fecha a
  // conexão em 300 s por padrão (requestTimeout).
  const server = app.getHttpServer();
  server.requestTimeout = 60 * 60 * 1000;
  server.headersTimeout = 65 * 1000;
  server.keepAliveTimeout = 65 * 1000;
  console.log(`serviço de ingestão em http://localhost:${PORT}`);
  console.log(`pipeline em ${pipelineDir()}`);
  console.log(`storage em ${storagePath()}${storagePathDefinido() ? '' : '  (STORAGE_PATH não definido — usando o padrão; veja www/.env.example)'}`);
}
bootstrap();
