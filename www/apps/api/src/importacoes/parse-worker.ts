/**
 * parse-worker.ts — Filho de child_process.fork() para S2.3
 *
 * Recebe { aqPath, importId } via process.on('message').
 * Lê STORAGE_PATH de process.env.
 * Extrai produtos + geometrias, grava arquivos no GeometryStore (disco),
 * e envia resultado via process.send().
 *
 * DatabaseSync (node:sqlite) bloqueia o event loop — por isso roda
 * em processo filho e não no handler NestJS.
 */

import { extract, extractSimboloias } from '../../../../tools/aq-reader';
import { toBuffers, OQ3DError } from '../../../../tools/oq3d-parser';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';

const STORAGE_PATH = path.resolve(
  process.env.STORAGE_PATH ?? path.join(process.cwd(), 'storage'),
);

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

async function run(input: WorkerInput): Promise<WorkerResult> {
  const { aqPath, importId } = input;

  const aqData = extract(aqPath);
  const { simbologias, porPeca } = extractSimboloias(aqPath);

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

  for (const peca of aqData.pecas) {
    const simId = porPeca.get(peca.ID_PECA);
    if (simId == null) continue;

    const simbologia = simbologias.get(simId);
    if (!simbologia) continue;

    let geoBuffer: Buffer;
    try {
      const buffers = toBuffers(simbologia.blob);
      geoBuffer = Buffer.from(JSON.stringify(buffers));
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

  if (products.length === 0) {
    return { status: 'vazio', productCount: 0 };
  }

  const hasCurvas = products.some((p) => p.curva && p.curva.length > 0);
  const layout = hasCurvas ? 'series-rows' : 'catalog-grid';

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

process.on('message', (msg: WorkerInput) => {
  run(msg)
    .then((result) => {
      process.send!(result);
      process.exit(0);
    })
    .catch((err: any) => {
      process.send!({ status: 'error', error: err.message ?? String(err) } satisfies WorkerResult);
      process.exit(1);
    });
});
