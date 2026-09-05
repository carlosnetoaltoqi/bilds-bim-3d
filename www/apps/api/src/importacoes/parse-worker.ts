/**
 * parse-worker.ts — Filho de child_process.fork() para S2.3
 *
 * Recebe { aqPath, importId } via process.on('message').
 * Resolve o storage com `common/storage-path.ts` (mesma regra da API).
 * Extrai produtos + geometrias, grava arquivos no GeometryStore (disco),
 * e envia resultado via process.send().
 *
 * DatabaseSync (node:sqlite) bloqueia o event loop — por isso roda
 * em processo filho e não no handler NestJS.
 */

import { extract, extractSimboloias } from '../../../../tools/aq-reader';
import { toBuffers, OQ3DBuffers, OQ3DError } from '../../../../tools/oq3d-parser';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { storagePath } from '../common/storage-path';

// Shared buffer for float32 bit-casting (float32 quantization matches Three.js Float32BufferAttribute)
const _f32ab = new ArrayBuffer(4);
const _f32view = new DataView(_f32ab);
function f32bits(v: number): number {
  _f32view.setFloat32(0, v, true);
  return _f32view.getUint32(0, true);
}

/**
 * Deduplicação de vértices com quantização float32 — equivalente ao scripts/dedup.py.
 * Redução típica: ~79% menos vértices, arquivo 3–5× menor.
 * Usa a mesma precisão do Float32BufferAttribute do Three.js como chave de lookup.
 */
function dedupBuffers(b: OQ3DBuffers): OQ3DBuffers {
  const { pos, col, idx } = b;
  const hasCol = col.length > 0;
  const seen = new Map<string, number>();
  const newPos: number[] = [];
  const newCol: number[] = [];
  const newIdx: number[] = [];

  for (const vi of idx) {
    const px = pos[vi * 3], py = pos[vi * 3 + 1], pz = pos[vi * 3 + 2];
    let key: string;
    if (hasCol) {
      const cr = col[vi * 3], cg = col[vi * 3 + 1], cb = col[vi * 3 + 2];
      key = `${f32bits(px)},${f32bits(py)},${f32bits(pz)},${f32bits(cr)},${f32bits(cg)},${f32bits(cb)}`;
    } else {
      key = `${f32bits(px)},${f32bits(py)},${f32bits(pz)}`;
    }
    let ni = seen.get(key);
    if (ni === undefined) {
      ni = newPos.length / 3;
      seen.set(key, ni);
      newPos.push(px, py, pz);
      if (hasCol) newCol.push(col[vi * 3], col[vi * 3 + 1], col[vi * 3 + 2]);
    }
    newIdx.push(ni);
  }

  return { pos: newPos, col: newCol, idx: newIdx };
}

const STORAGE_PATH = storagePath();

interface WorkerInput {
  aqPath: string;
  importId: string;
}

export interface ProductResult {
  id: string;
  nome: string;
  serie: string;
  specs: Record<string, string>;
  curva: number[][] | null;
  potencia: number | null;
  geoKey: string;
}

export interface CatalogMeta {
  titulo: string;
  fabricante: string;
  layout: string;
  filters: string[];
  slug: string;
}

export interface WorkerResult {
  status: 'ok' | 'vazio' | 'error';
  products?: ProductResult[];
  catalogMeta?: CatalogMeta;
  productCount?: number;
  error?: string;
}

function slugify(s: string): string {
  return (s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function ts() { return new Date().toISOString().slice(11, 23); }

async function run(input: WorkerInput): Promise<WorkerResult> {
  const { aqPath, importId } = input;
  const t0 = Date.now();
  const fileMb = (require('node:fs').statSync(aqPath).size / 1024 / 1024).toFixed(1);
  console.log(`[worker ${ts()}] início — ${fileMb} MB`);

  const aqData = extract(aqPath);
  console.log(`[worker ${ts()}] extract() concluído — ${((Date.now() - t0) / 1000).toFixed(1)}s — pecas=${aqData.pecas.length}`);

  const { simbologias, porPeca } = extractSimboloias(aqPath);
  console.log(`[worker ${ts()}] extractSimboloias() concluído — ${((Date.now() - t0) / 1000).toFixed(1)}s — simbologias=${simbologias.size}`);

  // Catalog metadata from CLASSE_SIMBOLOGIA_3D
  let classe = '';
  for (const s of simbologias.values()) {
    if (s.classe) { classe = s.classe; break; }
  }
  const sepIdx = classe.indexOf(' - ');
  const fabricante = (sepIdx >= 0 ? classe.slice(0, sepIdx) : classe).trim() || 'Desconhecido';
  const titulo = (sepIdx >= 0 ? classe.slice(sepIdx + 3) : classe).trim() || 'Catálogo';
  const catalogSlug = slugify(titulo);

  // Lookup maps
  const grupoMap = new Map(aqData.grupos.map((g) => [g.ID_GRUPO_PECA, g.NOME_GP]));

  const specsMap = new Map<number, Record<string, string>>();
  for (const prop of aqData.propriedades) {
    const s = specsMap.get(prop.ID_PECA) ?? {};
    s[prop.propriedade] = prop.VALOR;
    specsMap.set(prop.ID_PECA, s);
  }

  const curvaMap = new Map<number, number[][]>();
  for (const c of aqData.curvas) {
    const arr = curvaMap.get(c.ID_PECA) ?? [];
    arr.push([c.VAZAO_ICB, c.ALTURA_ICB, c.POTENCIA_ICB ?? 0, c.RENDIMENTO_ICB ?? 0]);
    curvaMap.set(c.ID_PECA, arr);
  }

  const potenciaMap = new Map<number, number>();
  for (const c of aqData.curvas) {
    if (!potenciaMap.has(c.ID_PECA) && c.potencia_cv != null) {
      potenciaMap.set(c.ID_PECA, c.potencia_cv);
    }
  }

  // Deduplicate product IDs within import
  const idCounts = new Map<string, number>();
  function uniqueId(base: string): string {
    const n = idCounts.get(base) ?? 0;
    idCounts.set(base, n + 1);
    return n === 0 ? base : `${base}-${n}`;
  }

  const products: ProductResult[] = [];
  const filters = new Set<string>();
  let geoCount = 0;

  for (const peca of aqData.pecas) {
    const simId = porPeca.get(peca.ID_PECA);
    if (simId == null) continue;

    const simbologia = simbologias.get(simId);
    if (!simbologia) continue;

    let geoBuffer: Buffer;
    let rawVertCount = 0;
    let dedupVertCount = 0;
    try {
      const raw = toBuffers(simbologia.blob);
      const deduped = dedupBuffers(raw);
      rawVertCount = raw.pos.length / 3;
      dedupVertCount = deduped.pos.length / 3;
      geoBuffer = Buffer.from(JSON.stringify(deduped));
    } catch (err) {
      if (err instanceof OQ3DError) continue;
      throw err;
    }

    const serie = grupoMap.get(peca.ID_GRUPO_PECA) ?? '';
    filters.add(serie);

    const baseId = slugify(peca.NOME_PECA) || `peca-${peca.ID_PECA}`;
    const id = uniqueId(baseId);
    const geoKey = `geo/${importId}/${id}.json`;

    const geoPath = path.join(STORAGE_PATH, geoKey);
    await fs.mkdir(path.dirname(geoPath), { recursive: true });
    await fs.writeFile(geoPath, geoBuffer);

    geoCount++;
    if (geoCount === 1 || geoCount % 50 === 0) {
      const pct = rawVertCount > 0 ? ((1 - dedupVertCount / rawVertCount) * 100).toFixed(0) : '0';
      console.log(`[worker ${ts()}] ${geoCount} geo gravadas — ${((Date.now() - t0) / 1000).toFixed(1)}s — ${(geoBuffer.length / 1024).toFixed(0)} KB (dedup -${pct}%)`);
    }

    products.push({
      id,
      nome: peca.NOME_PECA,
      serie,
      specs: specsMap.get(peca.ID_PECA) ?? {},
      curva: curvaMap.has(peca.ID_PECA) ? curvaMap.get(peca.ID_PECA)! : null,
      potencia: potenciaMap.get(peca.ID_PECA) ?? null,
      geoKey,
    });
  }

  console.log(`[worker ${ts()}] loop concluído — ${geoCount} geos em ${((Date.now() - t0) / 1000).toFixed(1)}s`);

  if (products.length === 0) {
    return { status: 'vazio', productCount: 0 };
  }

  const hasCurvas = products.some((p) => p.curva && p.curva.length > 0);
  const layout = hasCurvas ? 'series-rows' : 'catalog-grid';

  const totalSec = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`[worker ${ts()}] PRONTO — ${products.length} produtos — total ${totalSec}s`);

  return {
    status: 'ok',
    products,
    catalogMeta: {
      titulo,
      fabricante,
      layout,
      filters: [...filters],
      slug: catalogSlug,
    },
    productCount: products.length,
  };
}

// Pai morto (SIGKILL na API, por exemplo) fecha o canal IPC: sair já, em vez de terminar um
// parse de minutos e gravar centenas de JSONs em geo/<importId>/ que ninguém vai registrar
// (S7.13 — o RecuperacaoService limpa no boot, mas não pode competir com um órfão gravando).
process.on('disconnect', () => {
  console.error('parse-worker: o processo pai fechou o canal IPC — saindo (2)');
  process.exit(2);
});

process.on('message', (msg: WorkerInput) => {
  run(msg)
    .then((result) => {
      // Aguardar flush do IPC antes de sair — processo sair antes do flush perde
      // a mensagem quando o payload é grande (856 produtos = vários KB de IPC).
      process.send!(result, () => process.exit(0));
    })
    .catch((err: any) => {
      process.send!({ status: 'error', error: err.message ?? String(err) } satisfies WorkerResult, () => process.exit(1));
    });
});
