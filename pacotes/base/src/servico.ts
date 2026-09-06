/**
 * servico.ts — o `main.ts` que todo serviço Nest deste repositório tem em comum (ADR-001):
 * `.env`, porta vinda do env e validada, body parser com limite, `ValidationPipe` global, log
 * de cada requisição, CORS para o web, timeouts longos (uploads de centenas de MB, conversões de
 * minutos). Cada serviço só diz o seu nome, a variável da porta e o módulo raiz.
 */
import 'reflect-metadata';
import { INestApplication } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import * as dotenv from 'dotenv';
import { criarValidationPipe } from './validacao';

export interface OpcoesServico {
  /** nome nos logs (`ingestao`, `gerador-zip`…) */
  nome: string;
  /** variável de ambiente da porta e o padrão */
  envPorta: string;
  portaPadrao: number;
  /** caminho do `.env` a carregar antes de tudo (opcional) */
  envArquivo?: string;
  /** limite do body JSON (padrão `JSON_BODY_LIMIT` ou 300mb) */
  jsonLimit?: string;
  /** headers que o browser pode ler além dos padrão */
  exposedHeaders?: string[];
  /** o que imprimir depois de subir (ex.: onde está o storage) */
  aoSubir?: (app: INestApplication) => void | Promise<void>;
}

export function portaDoEnv(nome: string, padrao: number, env: NodeJS.ProcessEnv = process.env): number {
  const porta = Number(env[nome] ?? padrao);
  if (!Number.isInteger(porta) || porta <= 0 || porta > 65535) {
    throw new Error(`${nome} inválida: ${JSON.stringify(env[nome])} — use um inteiro entre 1 e 65535`);
  }
  return porta;
}

export function carregarEnv(arquivo?: string) {
  if (arquivo) dotenv.config({ path: arquivo });
}

export async function iniciarServico(modulo: any, opts: OpcoesServico): Promise<INestApplication> {
  const porta = portaDoEnv(opts.envPorta, opts.portaPadrao);
  const jsonLimit = opts.jsonLimit ?? process.env.JSON_BODY_LIMIT ?? '300mb';
  const app = await NestFactory.create<NestExpressApplication>(modulo, {
    logger: ['error', 'warn', 'log', 'verbose', 'debug'],
    bodyParser: false,
  });
  app.useBodyParser('json', { limit: jsonLimit });
  app.useBodyParser('urlencoded', { extended: true, limit: jsonLimit });
  app.useGlobalPipes(criarValidationPipe());
  app.use((req: any, res: any, next: any) => {
    const t = Date.now();
    const size = req.headers['content-length'] ? `${(+req.headers['content-length'] / 1024 / 1024).toFixed(1)} MB` : '-';
    res.on('finish', () => {
      if (req.url !== '/health') console.log(`[http] ${req.method} ${req.url} body=${size} → ${res.statusCode} (${Date.now() - t}ms)`);
    });
    next();
  });
  app.enableCors({
    origin: process.env.WEB_ORIGIN ?? 'http://localhost:3000',
    credentials: true,
    exposedHeaders: ['Content-Disposition', ...(opts.exposedHeaders ?? [])],
  });
  await app.listen(porta);
  const server = app.getHttpServer();
  server.requestTimeout = 60 * 60 * 1000;
  server.headersTimeout = 65 * 1000;
  server.keepAliveTimeout = 65 * 1000;
  console.log(`serviço ${opts.nome} em http://localhost:${porta}`);
  await opts.aoSubir?.(app);
  return app;
}
