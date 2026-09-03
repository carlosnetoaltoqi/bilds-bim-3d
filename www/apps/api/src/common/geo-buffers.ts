/**
 * geo-buffers.ts — contrato e validação do JSON de geometria do storage.
 *
 * O arquivo que o viewer consome é `{ pos, col, idx }`: posições em metros
 * (Y-up), cor RGB por vértice em 0..1 e índices de triângulos. O import grava
 * esse formato a partir do OQ3D (parse-worker.ts → toBuffers + dedupBuffers), e
 * o editor 3D (POC de edição) grava-o de volta pelo PUT /geometrias/:id.
 *
 * A validação aqui é o que impede um JSON malformado de derrubar o viewer de
 * todo visitante: comprimento múltiplo de 3, índices dentro do buffer, números
 * finitos. Não valida topologia — isso é papel do editor, que mostra arestas de
 * borda e triângulos degenerados antes de salvar.
 */

export interface GeoBuffers {
  pos: number[];
  col: number[];
  idx: number[];
}

export class GeoValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GeoValidationError';
  }
}

const MAX_VERTICES = 5_000_000;

export function validateGeoBuffers(body: unknown): GeoBuffers {
  if (!body || typeof body !== 'object') throw new GeoValidationError('corpo deve ser um objeto { pos, col, idx }');
  const b = body as Record<string, unknown>;

  const pos = b.pos;
  if (!Array.isArray(pos) || pos.length === 0) throw new GeoValidationError('"pos" deve ser um array não vazio');
  if (pos.length % 3 !== 0) throw new GeoValidationError(`"pos" tem ${pos.length} números — não é múltiplo de 3`);
  const nVerts = pos.length / 3;
  if (nVerts > MAX_VERTICES) throw new GeoValidationError(`${nVerts} vértices excede o limite de ${MAX_VERTICES}`);
  for (let i = 0; i < pos.length; i++) {
    const v = pos[i];
    if (typeof v !== 'number' || !Number.isFinite(v)) throw new GeoValidationError(`"pos[${i}]" não é um número finito`);
  }

  const col = b.col ?? [];
  if (!Array.isArray(col)) throw new GeoValidationError('"col" deve ser um array');
  if (col.length !== 0 && col.length !== pos.length) {
    throw new GeoValidationError(`"col" tem ${col.length} números; esperado 0 ou ${pos.length} (um RGB por vértice)`);
  }
  for (let i = 0; i < col.length; i++) {
    const v = col[i];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1) {
      throw new GeoValidationError(`"col[${i}]" deve estar em 0..1`);
    }
  }

  const idx = b.idx;
  if (!Array.isArray(idx) || idx.length === 0) throw new GeoValidationError('"idx" deve ser um array não vazio');
  if (idx.length % 3 !== 0) throw new GeoValidationError(`"idx" tem ${idx.length} índices — não é múltiplo de 3`);
  for (let i = 0; i < idx.length; i++) {
    const v = idx[i];
    if (!Number.isInteger(v) || v < 0 || v >= nVerts) {
      throw new GeoValidationError(`"idx[${i}]" = ${v} fora de 0..${nVerts - 1}`);
    }
  }

  return { pos: pos as number[], col: col as number[], idx: idx as number[] };
}

/** Estatísticas baratas para log e resposta do PUT. */
export function geoStats(g: GeoBuffers) {
  const nVerts = g.pos.length / 3;
  const nTris = g.idx.length / 3;
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let i = 0; i < g.pos.length; i += 3) {
    const x = g.pos[i], y = g.pos[i + 1], z = g.pos[i + 2];
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
    if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
  }
  return {
    vertices: nVerts,
    triangulos: nTris,
    bbox: { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] },
  };
}

/** Chave do backup do original: `geo/<importId>/<id>.orig.json` ao lado do arquivo vivo. */
export function originalKeyFor(geoKey: string): string {
  return geoKey.replace(/\.json$/, '') + '.orig.json';
}
