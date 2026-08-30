/**
 * oq3d-parser.ts — Port TypeScript de scripts/oq3d.py (S2.2)
 *
 * Lê o formato binário OQ3D ("OQ3D 3D Objects File"), a geometria 3D
 * embutida no BLOB SIMBOLOGIA_3D.SIMBOLOGIA_3D do AltoQi Builder.
 *
 * Diferenças deliberadas em relação ao Python:
 * - Lança OQ3DError (erro tipado) para blobs com assinatura ausente,
 *   contagem declarada maior que o buffer restante ou blob truncado —
 *   sem alocar nenhum array proporcional à contagem inválida.
 * - O Python retorna silenciosamente (return off) nessas situações.
 *
 * Unidades de entrada: centímetros, Z-up (AltoQi/IFC nativo).
 * Saída: metros, Y-up (Three.js), arrays flat prontos para BufferGeometry.
 */

const MAGIC = Buffer.from('OQ3D 3D Objects File');
const CM_TO_M = 0.01;
const OPEN = 0x5b;
const CLOSE = 0x5d;
const DEFAULT_RGBA: [number, number, number, number] = [150, 150, 150, 255];

const CLASSES = new Set([
  'TQi3DReusedObject',
  'TQi3DReusableObject',
  'TQi3DObjectGroup',
  'TQi3DTriangleMesh',
  'TCoatingColor',
  'TQi3DIndexedTriangleMeshData',
  'TCoordinateTransformation3D',
]);

// Bocais de conexão do AltoQi — marcadores, não geometria de produto
const MARKER_COLORS: Array<[number, number, number]> = [
  [1, 154, 63],
  [10, 84, 152],
  [0, 116, 232],
];

export class OQ3DError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OQ3DError';
  }
}

interface OQ3DNode {
  cls: string;
  children: OQ3DNode[];
  mesh: { verts: Array<[number, number, number]>; tris: Array<[number, number, number]> } | null;
  color: [number, number, number, number] | null;
  xform: { rot: number[]; trans: number[] } | null;
  guid: string | null;
}

export interface OQ3DBuffers {
  pos: number[];
  col: number[];
  idx: number[];
}

function makeNode(cls: string): OQ3DNode {
  return { cls, children: [], mesh: null, color: null, xform: null, guid: null };
}

/** True se o blob tem a assinatura OQ3D nos primeiros 64 bytes. */
export function isOQ3D(buf: Buffer): boolean {
  if (buf.length < 25) return false;
  const idx = buf.indexOf(MAGIC, 0);
  return idx >= 0 && idx < 64;
}

function classAt(buf: Buffer, p: number): { name: string; payloadOffset: number } | null {
  if (p + 5 > buf.length) return null;
  const length = buf.readUInt32LE(p + 1);
  if (length < 3 || length > 60 || p + 5 + length > buf.length) return null;
  const name = buf.toString('ascii', p + 5, p + 5 + length);
  return CLASSES.has(name) ? { name, payloadOffset: p + 5 + length } : null;
}

/**
 * Lê a malha indexada de um TQi3DIndexedTriangleMeshData.
 * Lança OQ3DError se a contagem declarada exceder o buffer —
 * sem alocar nenhum array antes da validação.
 * Retorna null para layout inválido não-malicioso (versão ≠ 2, zero coords, etc.)
 */
function readMesh(
  buf: Buffer,
  off: number,
): { verts: Array<[number, number, number]>; tris: Array<[number, number, number]>; endOffset: number } | null {
  const bufLen = buf.length;
  if (off + 12 > bufLen) throw new OQ3DError('blob truncado: header de malha além do buffer');

  const ver = buf.readUInt32LE(off);
  const nCoord = buf.readUInt32LE(off + 4);
  // off+8: reservado

  if (ver !== 2 || nCoord === 0 || nCoord % 3 !== 0) return null;

  // Segurança: validar tamanho ANTES de qualquer alocação
  const coordsEndOff = off + 12 + nCoord * 8;
  if (coordsEndOff + 8 > bufLen) {
    throw new OQ3DError(
      `blob truncado: ${nCoord} coords declarados × 8 bytes excedem o buffer restante`,
    );
  }

  const nIdx = buf.readUInt32LE(coordsEndOff);
  // coordsEndOff+4: reservado

  if (nIdx === 0 || nIdx % 3 !== 0) return null;

  const idxEndOff = coordsEndOff + 8 + nIdx * 4;
  if (idxEndOff > bufLen) {
    throw new OQ3DError(
      `blob truncado: ${nIdx} índices declarados × 4 bytes excedem o buffer restante`,
    );
  }

  // Seguro alocar
  const nVerts = nCoord / 3;
  const nTris = nIdx / 3;

  const verts: Array<[number, number, number]> = new Array(nVerts);
  for (let i = 0; i < nVerts; i++) {
    const base = off + 12 + i * 24;
    verts[i] = [buf.readDoubleLE(base), buf.readDoubleLE(base + 8), buf.readDoubleLE(base + 16)];
  }

  const tris: Array<[number, number, number]> = new Array(nTris);
  for (let i = 0; i < nTris; i++) {
    const base = coordsEndOff + 8 + i * 12;
    tris[i] = [
      buf.readUInt32LE(base),
      buf.readUInt32LE(base + 4),
      buf.readUInt32LE(base + 8),
    ];
  }

  return { verts, tris, endOffset: idxEndOff };
}

/** Devolve os nós-raiz da árvore de objetos OQ3D. */
export function parse(buf: Buffer): OQ3DNode[] {
  if (!isOQ3D(buf)) throw new OQ3DError('blob sem assinatura OQ3D');

  const roots: OQ3DNode[] = [];
  const stack: OQ3DNode[] = [];
  let p = 0;
  const n = buf.length;

  while (p < n) {
    const byte = buf[p];

    if (byte === OPEN) {
      const hit = classAt(buf, p);
      if (hit === null) {
        p++;
        continue;
      }
      const { name, payloadOffset: off } = hit;
      const node = makeNode(name);
      (stack.length ? stack[stack.length - 1].children : roots).push(node);
      stack.push(node);

      if (name === 'TCoatingColor') {
        // uint32 versao + uint32 flag + 4 bytes RGBA = offset 8
        node.color = [
          buf.readUInt8(off + 8),
          buf.readUInt8(off + 9),
          buf.readUInt8(off + 10),
          buf.readUInt8(off + 11),
        ];
        p = off + 12;
      } else if (name === 'TCoordinateTransformation3D') {
        // uint32 versao + 12 doubles (9 rot + 3 trans) = 4 + 96 = 100 bytes
        if (off + 4 + 96 <= n) {
          const rot: number[] = new Array(9);
          const trans: number[] = new Array(3);
          for (let i = 0; i < 9; i++) rot[i] = buf.readDoubleLE(off + 4 + i * 8);
          for (let i = 0; i < 3; i++) trans[i] = buf.readDoubleLE(off + 4 + 72 + i * 8);
          node.xform = { rot, trans };
        }
        p = off + 100;
      } else if (name === 'TQi3DIndexedTriangleMeshData') {
        const result = readMesh(buf, off);
        if (result !== null) {
          node.mesh = { verts: result.verts, tris: result.tris };
          p = result.endOffset;
        } else {
          p = off;
        }
      } else {
        if (name === 'TQi3DReusedObject' && off + 68 <= n) {
          try {
            if (buf.readUInt32LE(off + 28) === 36) {
              node.guid = buf.toString('ascii', off + 32, off + 68);
            }
          } catch {
            // guid é diagnóstico — ignorar falha
          }
        }
        p = off;
      }
      continue;
    }

    if (byte === CLOSE) {
      if (stack.length) stack.pop();
      p++;
      continue;
    }

    p++;
  }

  return roots;
}

function matMul(a: number[], b: number[]): number[] {
  const out: number[] = new Array(9);
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      out[r * 3 + c] = a[r * 3 + 0] * b[0 * 3 + c] + a[r * 3 + 1] * b[1 * 3 + c] + a[r * 3 + 2] * b[2 * 3 + c];
    }
  }
  return out;
}

function applyXform(rot: number[], trans: number[], v: [number, number, number]): [number, number, number] {
  return [
    rot[0] * v[0] + rot[1] * v[1] + rot[2] * v[2] + trans[0],
    rot[3] * v[0] + rot[4] * v[1] + rot[5] * v[2] + trans[1],
    rot[6] * v[0] + rot[7] * v[1] + rot[8] * v[2] + trans[2],
  ];
}

function collect(
  nodes: OQ3DNode[],
  rot: number[] | null,
  trans: number[] | null,
  color: [number, number, number, number] | null,
  out: Array<{ verts: Array<[number, number, number]>; tris: Array<[number, number, number]>; rgba: [number, number, number, number] }>,
): Array<{ verts: Array<[number, number, number]>; tris: Array<[number, number, number]>; rgba: [number, number, number, number] }> {
  for (const nd of nodes) {
    let own: { rot: number[]; trans: number[] } | null = null;
    let col = color;

    for (const ch of nd.children) {
      if (ch.cls === 'TCoordinateTransformation3D' && ch.xform !== null) {
        own = ch.xform;
      } else if (ch.cls === 'TCoatingColor' && ch.color !== null) {
        col = ch.color;
      }
    }

    let rot2: number[] | null;
    let trans2: number[] | null;

    if (own === null) {
      rot2 = rot;
      trans2 = trans;
    } else if (rot === null) {
      rot2 = own.rot;
      trans2 = own.trans;
    } else {
      rot2 = matMul(rot, own.rot);
      const t = applyXform(rot, trans!, [own.trans[0], own.trans[1], own.trans[2]]);
      trans2 = t;
    }

    if (nd.mesh !== null) {
      const { verts, tris } = nd.mesh;
      let worldVerts: Array<[number, number, number]>;
      if (rot2 === null) {
        worldVerts = verts;
      } else {
        worldVerts = verts.map((v) => applyXform(rot2!, trans2!, v));
      }
      out.push({ verts: worldVerts, tris, rgba: (col ?? DEFAULT_RGBA) as [number, number, number, number] });
    }

    collect(nd.children, rot2, trans2, col, out);
  }
  return out;
}

function isMarker(rgba: [number, number, number, number]): boolean {
  const r = rgba[0], g = rgba[1], b = rgba[2];
  return MARKER_COLORS.some(([mr, mg, mb]) => mr === r && mg === g && mb === b);
}

/**
 * Geometria indexada em metros, Y-up — mesmo contrato que oq3d.py:
 *   { pos: [...], col: [...], idx: [...] }
 *
 * @throws OQ3DError se o blob não tiver assinatura OQ3D ou estiver truncado.
 */
export function toBuffers(buf: Buffer, skipMarkers = false): OQ3DBuffers {
  const meshes = (function () {
    const raw = collect(parse(buf), null, null, null, []);
    if (skipMarkers) {
      const body = raw.filter((m) => !isMarker(m.rgba));
      return body.length ? body : raw;
    }
    return raw;
  })();

  const pos: number[] = [];
  const col: number[] = [];
  const idx: number[] = [];
  let base = 0;

  for (const { verts, tris, rgba } of meshes) {
    const r = rgba[0] / 255;
    const g = rgba[1] / 255;
    const b2 = rgba[2] / 255;

    for (const [vx, vy, vz] of verts) {
      // OQ3D: cm, Z-up → Three.js: m, Y-up
      // x → x, z → y, y → -z
      pos.push(vx * CM_TO_M, vz * CM_TO_M, -vy * CM_TO_M);
      col.push(r, g, b2);
    }
    for (const [i0, i1, i2] of tris) {
      idx.push(i0 + base, i1 + base, i2 + base);
    }
    base += verts.length;
  }

  return { pos, col, idx };
}
