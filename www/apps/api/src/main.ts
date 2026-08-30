import 'reflect-metadata';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Carrega www/.env antes de qualquer módulo NestJS
dotenv.config({ path: path.resolve(__dirname, '../../../.env') });

import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { logger: ['error', 'warn', 'log', 'verbose', 'debug'] });

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
  });
  await app.listen(4000);
  console.log('API rodando em http://localhost:4000');
}
bootstrap();
