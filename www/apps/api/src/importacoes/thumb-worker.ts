/**
 * thumb-worker.ts — worker de miniaturas (S2.4)
 *
 * Executado em processo filho via child_process.fork() pelo ImportacoesService.
 * Recebe via IPC:
 *   { products: Array<{ productId, geoKey }>, storagePath, importId }
 *
 * Para cada produto:
 *   1. Lê o geo JSON de storagePath/geoKey
 *   2. Renderiza WebP com o rasterizador TS (Abordagem B — ADR-003)
 *   3. Salva em storagePath/thumbs/{importId}/{productId}.webp
 *   4. Reporta { type: 'thumb', productId, thumbKey }
 *
 * Ao concluir: reporta { type: 'done', count }
 * Em erro individual: reporta { type: 'error', productId, message } e continua
 *
 * Falha de renderização nunca derruba a importação — miniaturas são opcionais.
 */

import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { renderThumbTs } from '../../../../tools/thumb-rasterizer';

export interface ThumbWorkerInput {
  products: Array<{ productId: string; geoKey: string }>;
  storagePath: string;
  importId: string;
}

export type ThumbWorkerMessage =
  | { type: 'thumb'; productId: string; thumbKey: string }
  | { type: 'done'; count: number }
  | { type: 'error'; productId: string; message: string };

process.on('message', async (msg: ThumbWorkerInput) => {
  const { products, storagePath, importId } = msg;
  let count = 0;

  for (const { productId, geoKey } of products) {
    try {
      const geoPath = path.join(storagePath, geoKey);
      const raw = await fs.readFile(geoPath, 'utf8');
      const geoData = JSON.parse(raw);

      const webpBuf = await renderThumbTs(geoData);

      const thumbDir = path.join(storagePath, 'thumbs', importId);
      await fs.mkdir(thumbDir, { recursive: true });

      const thumbKey = `thumbs/${importId}/${productId}.webp`;
      const thumbPath = path.join(storagePath, thumbKey);
      await fs.writeFile(thumbPath, webpBuf);

      count++;
      process.send!({ type: 'thumb', productId, thumbKey } satisfies ThumbWorkerMessage);
    } catch (err: any) {
      process.send!({
        type: 'error',
        productId,
        message: err.message ?? String(err),
      } satisfies ThumbWorkerMessage);
    }
  }

  // Aguarda flush do IPC antes de sair — evita perda de payload em respostas grandes
  process.send!({ type: 'done', count } satisfies ThumbWorkerMessage, () => process.exit(0));
});
