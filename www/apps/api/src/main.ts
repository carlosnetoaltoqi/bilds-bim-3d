import 'reflect-metadata';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Carrega www/.env antes de qualquer módulo NestJS
dotenv.config({ path: path.resolve(__dirname, '../../../.env') });

import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from './app.module';
import { storagePath, storagePathDefinido } from '@bim/dominio';
import { criarValidationPipe } from '@bim/dominio';

// A geometria editada volta pelo PUT /geometrias/:id como JSON. Uma peça grande
// (Maxbar) passa de 10 MB; o limite padrão do express é 100 KB.
const JSON_BODY_LIMIT = process.env.JSON_BODY_LIMIT ?? '300mb';
// Porta da API (I17): `PORT` no www/.env; o web aponta para ela via NEXT_PUBLIC_API_URL/API_URL.
const PORT = Number(process.env.PORT ?? 4000);
if (!Number.isInteger(PORT) || PORT <= 0 || PORT > 65535) {
  throw new Error(`PORT inválida: ${JSON.stringify(process.env.PORT)} — use um inteiro entre 1 e 65535`);
}

async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    logger: ['error', 'warn', 'log', 'verbose', 'debug'],
    bodyParser: false,
  });
  app.useBodyParser('json', { limit: JSON_BODY_LIMIT });
  app.useBodyParser('urlencoded', { extended: true, limit: JSON_BODY_LIMIT });
  // Corpos com DTO são validados e limpos aqui (I16); ver common/validation.ts
  app.useGlobalPipes(criarValidationPipe());

  // HTTP request logger
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
  // Conversão de CAD grande pode levar minutos; o Node fecha a conexão em 300 s por padrão
  // (requestTimeout) e o browser vê "Failed to fetch". A importação virou assíncrona, mas
  // /cad/tesselar (síncrono, usado pelo editor) e uploads grandes precisam de folga.
  const server = app.getHttpServer();
  server.requestTimeout = 60 * 60 * 1000;
  server.headersTimeout = 65 * 1000;
  server.keepAliveTimeout = 65 * 1000;
  console.log(`API rodando em http://localhost:${PORT}`);
  console.log(`storage em ${storagePath()}${storagePathDefinido() ? '' : '  (STORAGE_PATH não definido — usando o padrão; veja www/.env.example)'}`);
}
bootstrap();
