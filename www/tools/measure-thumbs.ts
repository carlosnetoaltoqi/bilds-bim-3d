/**
 * measure-thumbs.ts — S2.4: medição comparativa das abordagens de thumbnail
 *
 * Mede as duas abordagens da seção 7.4 do plano sobre os 13 produtos Dancor:
 *
 *   A — Playwright + Chromium + SwiftShader (mesmo motor do thumbs.mjs)
 *   B — Rasterizador TS (thumb-rasterizer.ts) + ffmpeg → WebP
 *
 * Saída: tabela com tempo por geometria, pico de memória e tamanho do WebP.
 * Os resultados alimentam o ADR-003 do plano.
 *
 * Uso:
 *   pnpm thumb:measure
 */

import * as dotenv from 'dotenv';
import * as path from 'node:path';
import * as fs from 'node:fs/promises';
import { existsSync, createReadStream } from 'node:fs';
import { createServer } from 'node:http';
import { MongoClient } from 'mongodb';
import { renderThumbTs, RasterBuffers, THUMB_W, THUMB_H } from './thumb-rasterizer';

// .env fica em www/ (gitignored)
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const MONGODB_URI = process.env.MONGODB_URI!;
const MONGODB_DB = process.env.MONGODB_DB ?? 'bilds-bim-3d';
const STORAGE_PATH = path.resolve(__dirname, '../apps/api', process.env.STORAGE_PATH ?? '../../storage/bim');

if (!MONGODB_URI) {
  console.error('MONGODB_URI não definido — verifique www/apps/api/.env ou www/.env');
  process.exit(1);
}

// ── Playwright (opcional — só mede se disponível) ───────────────────────────
let playwright: any = null;
try {
  // playwright está em bilds-bim-3d/node_modules/ — dois níveis acima de www/tools/
  const playwrightPath = path.resolve(__dirname, '../../node_modules/playwright');
  playwright = require(playwrightPath);
} catch {
  console.warn('[A] playwright não encontrado — pulando Abordagem A');
}

// Servidor HTTP mínimo para servir arquivos do storage (harness busca via fetch)
function startServer(root: string): Promise<{ port: number; close: () => void }> {
  return new Promise((resolve, reject) => {
    const MIMES: Record<string, string> = {
      '.html': 'text/html; charset=utf-8',
      '.js': 'text/javascript; charset=utf-8',
      '.mjs': 'text/javascript; charset=utf-8',
      '.json': 'application/json; charset=utf-8',
    };
    const srv = createServer((req, res) => {
      const urlPath = decodeURIComponent(new URL(req.url!, 'http://x').pathname);
      const filePath = path.resolve(path.join(root, urlPath));
      if (!filePath.startsWith(path.resolve(root)) || !existsSync(filePath)) {
        res.writeHead(404).end();
        return;
      }
      const ext = path.extname(filePath);
      res.writeHead(200, { 'Content-Type': MIMES[ext] ?? 'application/octet-stream' });
      createReadStream(filePath).pipe(res);
    });
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address() as { port: number };
      resolve({ port: addr.port, close: () => srv.close() });
    });
  });
}

interface GeoData extends RasterBuffers {}

interface Measurement {
  geoKey: string;
  bytesWebP: number;
  elapsedMs: number;
  heapDeltaMB: number;
}

// ── Medição Abordagem B ──────────────────────────────────────────────────────
async function measureB(geoData: GeoData): Promise<Measurement & { geoKey: string }> {
  const geoKey = 'geo/measure';
  const t0 = performance.now();
  const h0 = process.memoryUsage().heapUsed;
  const buf = await renderThumbTs(geoData);
  const h1 = process.memoryUsage().heapUsed;
  const t1 = performance.now();
  return {
    geoKey,
    bytesWebP: buf.length,
    elapsedMs: t1 - t0,
    heapDeltaMB: (h1 - h0) / 1024 / 1024,
  };
}

// ── Medição Abordagem A ──────────────────────────────────────────────────────
async function measureAllA(
  products: Array<{ geoKey: string }>,
): Promise<Measurement[]> {
  if (!playwright) return [];
  const { chromium } = playwright;

  // Serve a partir da raiz do repo (harness busca /templates/thumbs/harness.html)
  // www/tools/ → ../.. = bilds-bim-3d/
  const repoRoot = path.resolve(__dirname, '../..');
  const { port, close } = await startServer(repoRoot);

  let browser: any;
  try {
    browser = await chromium.launch({
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    });
  } catch (err: any) {
    close();
    console.warn('[A] Chromium não inicializou:', err.message?.split('\n')[0]);
    return [];
  }

  const results: Measurement[] = [];
  try {
    const page = await browser.newPage();
    page.on('pageerror', (e: Error) => console.error('[A pageerror]', e.message));

    await page.goto(`http://127.0.0.1:${port}/templates/thumbs/harness.html`, {
      waitUntil: 'load',
    });
    await page.waitForFunction('window.__thumbReady === true', { timeout: 30_000 });

    for (const p of products) {
      // URL do geo file servido pelo servidor local
      const geoUrl =
        '/' +
        path.relative(repoRoot, path.join(STORAGE_PATH, p.geoKey))
          .split(/[\\/]/)
          .map(encodeURIComponent)
          .join('/');

      const t0 = performance.now();
      const h0 = process.memoryUsage().heapUsed;

      let bytesWebP = 0;
      try {
        const dataUrl = await page.evaluate(
          ([u, w, h, m, q]: [string, number, number, string, number]) =>
            (window as any).renderThumb(u, w, h, m, q),
          [geoUrl, THUMB_W, THUMB_H, 'image/webp', 0.85] as [string, number, number, string, number],
        );
        const b64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
        bytesWebP = Buffer.from(b64, 'base64').length;
      } catch (err: any) {
        console.warn(`[A] erro em ${p.geoKey}:`, err.message);
      }

      const h1 = process.memoryUsage().heapUsed;
      const t1 = performance.now();
      results.push({
        geoKey: p.geoKey,
        bytesWebP,
        elapsedMs: t1 - t0,
        heapDeltaMB: (h1 - h0) / 1024 / 1024,
      });
    }
  } finally {
    await browser.close();
    close();
  }
  return results;
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const db = client.db(MONGODB_DB);

  // Pega todos os produtos com geoKey (de qualquer importação, ordenados por nome)
  const products = await db
    .collection('bim_products')
    .find({ geoKey: { $exists: true, $ne: null } })
    .sort({ nome: 1 })
    .toArray();

  if (products.length === 0) {
    console.error('Nenhum produto com geoKey encontrado. Execute o upload do Dancor primeiro.');
    await client.close();
    process.exit(1);
  }

  console.log(`\n[S2.4] Medindo ${products.length} produtos...\n`);

  // ── Abordagem B ─────────────────────────────────────────────────────────────
  console.log('=== Abordagem B: Rasterizador TS + ffmpeg ===');
  const resultsB: Measurement[] = [];
  for (const p of products) {
    const geoPath = path.join(STORAGE_PATH, p.geoKey as string);
    let geoData: GeoData;
    try {
      const raw = await fs.readFile(geoPath, 'utf8');
      geoData = JSON.parse(raw);
    } catch (err: any) {
      console.warn(`[B] erro ao ler ${p.geoKey}: ${err.message}`);
      continue;
    }

    process.stdout.write(`  ${p.nome} ... `);
    const m = await measureB(geoData);
    m.geoKey = p.geoKey as string;
    resultsB.push(m);
    console.log(
      `${m.elapsedMs.toFixed(0)} ms | heap Δ${m.heapDeltaMB.toFixed(1)} MB | ${(m.bytesWebP / 1024).toFixed(1)} KB`,
    );
  }

  // ── Abordagem A ─────────────────────────────────────────────────────────────
  console.log('\n=== Abordagem A: Playwright + Chromium + SwiftShader ===');
  const resultsA = await measureAllA(
    products.map((p) => ({ geoKey: p.geoKey as string })),
  );
  if (resultsA.length === 0 && playwright) {
    console.log('  Nenhum resultado — Chromium não inicializou.');
  }
  for (const m of resultsA) {
    const name = products.find((p) => p.geoKey === m.geoKey)?.nome ?? m.geoKey;
    console.log(
      `  ${name}: ${m.elapsedMs.toFixed(0)} ms | heap Δ${m.heapDeltaMB.toFixed(1)} MB | ${(m.bytesWebP / 1024).toFixed(1)} KB`,
    );
  }

  // ── Tabela resumo ───────────────────────────────────────────────────────────
  console.log('\n=== RESUMO ===');
  const avgB = resultsB.length
    ? {
        ms: avg(resultsB.map((r) => r.elapsedMs)),
        heap: avg(resultsB.map((r) => r.heapDeltaMB)),
        kb: avg(resultsB.map((r) => r.bytesWebP / 1024)),
      }
    : null;
  const avgA = resultsA.length
    ? {
        ms: avg(resultsA.map((r) => r.elapsedMs)),
        heap: avg(resultsA.map((r) => r.heapDeltaMB)),
        kb: avg(resultsA.map((r) => r.bytesWebP / 1024)),
      }
    : null;

  console.log('');
  console.log('| Abordagem | Média ms/geo | Heap Δ MB | KB/WebP |');
  console.log('|-----------|-------------|-----------|---------|');
  if (avgB) {
    console.log(
      `| B (TS)    | ${avgB.ms.toFixed(0).padStart(11)} | ${avgB.heap.toFixed(1).padStart(9)} | ${avgB.kb.toFixed(1).padStart(7)} |`,
    );
  }
  if (avgA) {
    console.log(
      `| A (PW)    | ${avgA.ms.toFixed(0).padStart(11)} | ${avgA.heap.toFixed(1).padStart(9)} | ${avgA.kb.toFixed(1).padStart(7)} |`,
    );
  }
  if (!avgB && !avgA) {
    console.log('Nenhum resultado obtido.');
  }
  if (avgB && avgA) {
    const ratio = avgA.ms / avgB.ms;
    console.log(
      `\nB é ${ratio > 1 ? ratio.toFixed(1) + '× mais rápido' : (1 / ratio).toFixed(1) + '× mais lento'} que A por geometria.`,
    );
  }
  console.log('');

  await client.close();
}

function avg(arr: number[]): number {
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
