/**
 * S2.1 — Spike da fronteira: testa o Python worker HTTP end-to-end
 *
 * Uso: pnpm worker:test
 * Encerra com código 0 se tudo passou, 1 se falhou.
 */

import * as path from 'path';
import * as fs from 'fs/promises';
import * as fsSync from 'fs';
import * as crypto from 'crypto';
import * as http from 'http';
import { spawn } from 'child_process';
import * as dotenv from 'dotenv';
import { MongoClient } from 'mongodb';

dotenv.config({ path: path.resolve(__dirname, '../.env') });

const WORKER_PORT = parseInt(process.env.WORKER_PORT ?? '5001', 10);
const WORKER_DIR  = path.resolve(__dirname, '../workers/aq-parser');
const WORKER_PATH = path.join(WORKER_DIR, 'worker.py');
const VENV_PYTHON = path.join(WORKER_DIR, '.venv/bin/python3');
const AQ_PATH     = path.resolve(__dirname, '../../input/Dancor/pecas_dancor_bombas_incendio_2026_04.1.aq');
const STORAGE_PATH = path.resolve(__dirname, '../storage/bim');

const PYTHON_BIN = fsSync.existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python3';

function httpGet(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => (res.statusCode === 200 ? resolve(data) : reject(new Error(`HTTP ${res.statusCode}`))));
    }).on('error', reject);
  });
}

function httpPost(
  url: string,
  body: Buffer,
  headers: Record<string, string>,
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: Number(parsed.port),
        path: parsed.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/octet-stream',
          'Content-Length': body.length,
          ...headers,
        },
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => resolve({ status: res.statusCode ?? 0, body: data }));
      },
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function run() {
  const uri = process.env.MONGODB_URI;
  if (!uri) throw new Error('MONGODB_URI não definido em www/.env');

  const importId  = crypto.randomUUID();
  const catalogId = crypto.randomUUID();
  const companyId = crypto.randomUUID();

  const worker = spawn(PYTHON_BIN, [WORKER_PATH], {
    env: { ...process.env, STORAGE_PATH, WORKER_PORT: String(WORKER_PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let workerExited = false;
  worker.on('exit', () => { workerExited = true; });
  worker.stderr?.on('data', (d: Buffer) => process.stderr.write(d));
  worker.stdout?.on('data', (d: Buffer) => process.stdout.write(d));

  const t0 = Date.now();

  try {
    // Poll health with early crash detection
    for (let i = 0; i < 20; i++) {
      if (workerExited) throw new Error('Worker subprocess crashed at startup');
      try {
        await httpGet(`http://localhost:${WORKER_PORT}/health`);
        break;
      } catch {
        if (i === 19) throw new Error('Worker did not become healthy after 10s');
        await new Promise((r) => setTimeout(r, 500));
      }
    }

    // POST /parse with the .aq
    const aqData = await fs.readFile(AQ_PATH);
    const { status: httpStatus, body: responseRaw } = await httpPost(
      `http://localhost:${WORKER_PORT}/parse`,
      aqData,
      {
        'X-Import-Id': importId,
        'X-Company-Id': companyId,
        'X-Catalog-Id': catalogId,
        'X-File-Name': 'pecas_dancor_bombas_incendio_2026_04.1.aq',
      },
    );
    const elapsed = Date.now() - t0;

    if (httpStatus !== 200) {
      throw new Error(`Worker HTTP ${httpStatus}: ${responseRaw}`);
    }
    const response = JSON.parse(responseRaw);

    if (response.status !== 'ok') {
      throw new Error(`Worker status=${response.status}: ${response.error ?? '(sem detalhe)'}`);
    }
    if (response.productCount !== 13) {
      throw new Error(`Esperado productCount=13, obtido=${response.productCount}`);
    }

    // Verify disk
    const geoDir = path.join(STORAGE_PATH, 'geo', importId);
    const files = await fs.readdir(geoDir);
    if (files.length !== 13) {
      throw new Error(`Esperado 13 arquivos em disco, obtido=${files.length} em ${geoDir}`);
    }

    // Verify DB
    const mongo = new MongoClient(uri);
    await mongo.connect();
    const db = mongo.db(process.env.MONGODB_DB ?? 'bilds-bim-3d');
    const count = await db.collection('bim_products').countDocuments({ importId });
    await mongo.close();
    if (count !== 13) {
      throw new Error(`Esperado 13 documentos no Atlas, obtido=${count}`);
    }

    // Print metrics table
    console.log('\n┌─ S2.1 — Spike da fronteira: Python worker HTTP ──────────┐');
    console.log(`│  productCount   : ${String(response.productCount).padStart(6)}`);
    console.log(`│  peakMemoryMb   : ${String(response.peakMemoryMb).padStart(6)} MB  (RSS delta, nível OS)`);
    console.log(`│  peakTraceMb    : ${String(response.peakTraceMb).padStart(6)} MB  (tracemalloc heap Python)`);
    console.log(`│  elapsedWorker  : ${String(response.elapsedMs).padStart(6)} ms  (dentro do worker)`);
    console.log(`│  elapsedTotal   : ${String(elapsed).padStart(6)} ms  (inc. spawn + health poll + POST)`);
    console.log(`│  importId       : ${importId}`);
    console.log('└───────────────────────────────────────────────────────────┘');
    console.log('\npnpm worker:test ✓ — todas as verificações passaram\n');
  } finally {
    worker.kill('SIGTERM');
  }
}

run().catch((err) => {
  console.error('\nERRO:', err.message);
  process.exit(1);
});
