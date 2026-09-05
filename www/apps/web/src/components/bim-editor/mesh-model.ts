/**
 * mesh-model.ts — modelo de edição da geometria de um produto.
 *
 * O storage guarda um JSON plano `{ pos, col, idx }` (metros, Y-up, cor por
 * vértice), e a hierarquia do OQ3D (malhas, transforms, instâncias) se perde no
 * import. Para editar, este módulo RE-SEGMENTA a malha em "partes": componentes
 * conexos do grafo de triângulos. Como o dedup do import só funde vértices de
 * mesma posição E mesma cor, dois triângulos de cores diferentes nunca
 * compartilham índice — logo cada componente sai com cor uniforme, e o conjunto
 * de componentes aproxima as malhas originais do `.aq` (uma TQi3DTriangleMesh
 * vira uma ou mais partes; partes soldadas por vértice viram uma só).
 *
 * Os bocais de conexão do AltoQi — verde (1,154,63), azul (10,84,152) e azul
 * (0,116,232) — são marcadores, não produto; ficam sinalizados em `marker`.
 *
 * Cada parte carrega seus vértices em coordenadas locais (as do JSON, na
 * segmentação) mais uma matriz 4×4. Editar é mexer na matriz, na cor, na
 * visibilidade ou substituir os buffers. `bake()` aplica as matrizes, concatena
 * e deduplica com a MESMA quantização float32 do parse-worker, devolvendo um
 * `{ pos, col, idx }` pronto para o PUT /geometrias/:id.
 *
 * Tudo aqui é puro (sem React, sem WebGL). O Three.js entra só por Matrix4/Vector3.
 */

import * as THREE from 'three'
import type { GeoData } from '../bim-catalog/bim-viewer-engine'

export type RGB = [number, number, number]

export interface Part {
  /** id estável dentro da sessão de edição */
  id: string
  nome: string
  /** posições locais, xyz intercalado, metros */
  pos: Float32Array
  /** rgb por vértice em 0..1, ou null (sem cor → cinza do viewer) */
  col: Float32Array | null
  idx: Uint32Array
  /** 4×4 column-major, como THREE.Matrix4.elements */
  matrix: number[]
  visible: boolean
  /** bocal de conexão do AltoQi (detectado pela cor) */
  marker: boolean
}

export interface PartStats {
  vertices: number
  triangulos: number
  /** arestas com um só triângulo — 0 em sólido fechado */
  arestasBorda: number
  /** arestas com mais de dois triângulos */
  arestasNaoManifold: number
  triangulosDegenerados: number
  /** bbox em coordenadas de mundo (matriz aplicada), metros */
  bbox: THREE.Box3
  /** cor dominante (primeiro vértice) ou null */
  cor: RGB | null
}

const MARKER_COLORS: RGB[] = [
  [1, 154, 63],
  [10, 84, 152],
  [0, 116, 232],
]

export const IDENTITY: number[] = new THREE.Matrix4().identity().toArray()

let _seq = 0
export function novoId(prefix = 'p'): string {
  _seq += 1
  return `${prefix}-${Date.now().toString(36)}-${_seq}`
}

// ─── Segmentação ──────────────────────────────────────────────────────────────

class UnionFind {
  parent: Int32Array
  constructor(n: number) {
    this.parent = new Int32Array(n)
    for (let i = 0; i < n; i++) this.parent[i] = i
  }
  find(a: number): number {
    let r = a
    while (this.parent[r] !== r) r = this.parent[r]
    while (this.parent[a] !== r) {
      const nx = this.parent[a]
      this.parent[a] = r
      a = nx
    }
    return r
  }
  union(a: number, b: number) {
    const ra = this.find(a), rb = this.find(b)
    if (ra !== rb) this.parent[rb] = ra
  }
}

function isMarkerColor(r: number, g: number, b: number): boolean {
  const R = Math.round(r * 255), G = Math.round(g * 255), B = Math.round(b * 255)
  return MARKER_COLORS.some(([mr, mg, mb]) => mr === R && mg === G && mb === B)
}

/**
 * Divide `{pos,col,idx}` em partes por componentes conexos de triângulos.
 * Ordena as partes por número de triângulos (maior primeiro) e nomeia-as
 * "Parte 1..N"; bocais recebem "Bocal N".
 */
export function segment(geo: GeoData): Part[] {
  const pos = geo.pos
  const col = geo.col && geo.col.length === pos.length ? geo.col : null
  const idx = geo.idx ?? Array.from({ length: pos.length / 3 }, (_, i) => i)
  const nVerts = pos.length / 3
  const uf = new UnionFind(nVerts)
  for (let t = 0; t < idx.length; t += 3) {
    uf.union(idx[t], idx[t + 1])
    uf.union(idx[t], idx[t + 2])
  }

  // agrupa triângulos por raiz
  const groups = new Map<number, number[]>() // root → lista de triângulos (offset t)
  for (let t = 0; t < idx.length; t += 3) {
    const root = uf.find(idx[t])
    let arr = groups.get(root)
    if (!arr) {
      arr = []
      groups.set(root, arr)
    }
    arr.push(t)
  }

  const parts: Part[] = []
  for (const tris of groups.values()) {
    const remap = new Map<number, number>()
    const p: number[] = []
    const c: number[] = []
    const ix: number[] = []
    for (const t of tris) {
      for (let k = 0; k < 3; k++) {
        const vi = idx[t + k]
        let ni = remap.get(vi)
        if (ni === undefined) {
          ni = p.length / 3
          remap.set(vi, ni)
          p.push(pos[vi * 3], pos[vi * 3 + 1], pos[vi * 3 + 2])
          if (col) c.push(col[vi * 3], col[vi * 3 + 1], col[vi * 3 + 2])
        }
        ix.push(ni)
      }
    }
    const marker = col ? isMarkerColor(c[0], c[1], c[2]) : false
    parts.push({
      id: novoId(),
      nome: '',
      pos: new Float32Array(p),
      col: col ? new Float32Array(c) : null,
      idx: new Uint32Array(ix),
      matrix: [...IDENTITY],
      visible: true,
      marker,
    })
  }

  parts.sort((a, b) => b.idx.length - a.idx.length)
  let nPart = 0, nBocal = 0
  for (const part of parts) {
    part.nome = part.marker ? `Bocal ${++nBocal}` : `Parte ${++nPart}`
  }
  return parts
}

// ─── Estatísticas e diagnóstico ──────────────────────────────────────────────

const _v = new THREE.Vector3()
const _m = new THREE.Matrix4()

export function partStats(part: Part): PartStats {
  const { pos, idx } = part
  const edges = new Map<number, number>() // chave a*nV+b (a<b) → contagem
  const nV = pos.length / 3
  let degenerados = 0
  for (let t = 0; t < idx.length; t += 3) {
    const a = idx[t], b = idx[t + 1], c = idx[t + 2]
    if (a === b || b === c || a === c) {
      degenerados++
      continue
    }
    for (const [u, w] of [[a, b], [b, c], [c, a]] as const) {
      const lo = u < w ? u : w, hi = u < w ? w : u
      const key = lo * nV + hi
      edges.set(key, (edges.get(key) ?? 0) + 1)
    }
  }
  let borda = 0, naoManifold = 0
  for (const n of edges.values()) {
    if (n === 1) borda++
    else if (n > 2) naoManifold++
  }
  return {
    vertices: nV,
    triangulos: idx.length / 3,
    arestasBorda: borda,
    arestasNaoManifold: naoManifold,
    triangulosDegenerados: degenerados,
    bbox: worldBbox(part),
    cor: part.col ? [part.col[0], part.col[1], part.col[2]] : null,
  }
}

export function worldBbox(part: Part): THREE.Box3 {
  const box = new THREE.Box3()
  _m.fromArray(part.matrix)
  const { pos } = part
  for (let i = 0; i < pos.length; i += 3) {
    _v.set(pos[i], pos[i + 1], pos[i + 2]).applyMatrix4(_m)
    box.expandByPoint(_v)
  }
  return box
}

export function docBbox(parts: Part[], somenteVisiveis = true): THREE.Box3 {
  const box = new THREE.Box3()
  for (const p of parts) {
    if (somenteVisiveis && !p.visible) continue
    box.union(worldBbox(p))
  }
  return box
}

// ─── Operações sobre partes (todas devolvem objetos novos) ───────────────────

export function withMatrix(part: Part, matrix: number[]): Part {
  return { ...part, matrix: [...matrix] }
}

export function recolor(part: Part, rgb: RGB): Part {
  const n = part.pos.length
  const col = new Float32Array(n)
  for (let i = 0; i < n; i += 3) {
    col[i] = rgb[0]
    col[i + 1] = rgb[1]
    col[i + 2] = rgb[2]
  }
  return { ...part, col, marker: isMarkerColor(rgb[0], rgb[1], rgb[2]) }
}

/** Inverte o sentido dos triângulos (normais para o outro lado). */
export function flipNormals(part: Part): Part {
  const idx = new Uint32Array(part.idx.length)
  for (let t = 0; t < idx.length; t += 3) {
    idx[t] = part.idx[t]
    idx[t + 1] = part.idx[t + 2]
    idx[t + 2] = part.idx[t + 1]
  }
  return { ...part, idx }
}

/** Aplica a matriz nos vértices e zera a matriz. */
export function bakeMatrix(part: Part): Part {
  _m.fromArray(part.matrix)
  const pos = new Float32Array(part.pos.length)
  for (let i = 0; i < pos.length; i += 3) {
    _v.set(part.pos[i], part.pos[i + 1], part.pos[i + 2]).applyMatrix4(_m)
    pos[i] = _v.x
    pos[i + 1] = _v.y
    pos[i + 2] = _v.z
  }
  const det = _m.determinant()
  const baked = { ...part, pos, matrix: [...IDENTITY] }
  // escala negativa (espelho) inverte o sentido dos triângulos — corrige
  return det < 0 ? flipNormals(baked) : baked
}

/**
 * Espelha a parte no eixo dado. `origem = 'propria'` espelha em torno do centro
 * da própria bbox (a parte fica no lugar, invertida); `'mundo'` em torno do
 * plano que passa pela origem.
 */
export function mirror(part: Part, eixo: 'x' | 'y' | 'z', origem: 'propria' | 'mundo'): Part {
  const baked = bakeMatrix(part)
  const c = origem === 'propria' ? worldBbox(baked).getCenter(new THREE.Vector3()) : new THREE.Vector3()
  const k = eixo === 'x' ? 0 : eixo === 'y' ? 1 : 2
  const cc = eixo === 'x' ? c.x : eixo === 'y' ? c.y : c.z
  const pos = new Float32Array(baked.pos)
  for (let i = k; i < pos.length; i += 3) pos[i] = 2 * cc - pos[i]
  return flipNormals({ ...baked, pos })
}

/** Funde várias partes numa só (mantém cores por vértice). */
export function mergeParts(parts: Part[], nome?: string): Part {
  const baked = parts.map(bakeMatrix)
  let nPos = 0, nIdx = 0
  for (const p of baked) {
    nPos += p.pos.length
    nIdx += p.idx.length
  }
  const anyCol = baked.some((p) => p.col)
  const pos = new Float32Array(nPos)
  const col = anyCol ? new Float32Array(nPos) : null
  const idx = new Uint32Array(nIdx)
  let po = 0, io = 0
  for (const p of baked) {
    pos.set(p.pos, po)
    if (col) {
      if (p.col) col.set(p.col, po)
      else for (let i = po; i < po + p.pos.length; i += 3) { col[i] = 0.533; col[i + 1] = 0.588; col[i + 2] = 0.667 }
    }
    const base = po / 3
    for (let i = 0; i < p.idx.length; i++) idx[io + i] = p.idx[i] + base
    po += p.pos.length
    io += p.idx.length
  }
  return {
    id: novoId(),
    nome: nome ?? `${parts[0].nome} + ${parts.length - 1}`,
    pos, col, idx,
    matrix: [...IDENTITY],
    visible: true,
    marker: false,
  }
}

/** Compõe `m` (mundo) sobre todas as partes: transformação global. */
export function transformAll(parts: Part[], m: THREE.Matrix4): Part[] {
  return parts.map((p) => {
    const own = new THREE.Matrix4().fromArray(p.matrix)
    return { ...p, matrix: own.premultiply(m).toArray() }
  })
}

/**
 * Recentra o modelo: `centro` põe o centro da bbox na origem; `base` põe o
 * centro XZ na origem e a face inferior em y=0.
 */
export function recenter(parts: Part[], modo: 'centro' | 'base'): Part[] {
  const box = docBbox(parts, false)
  if (box.isEmpty()) return parts
  const c = box.getCenter(new THREE.Vector3())
  const t = modo === 'centro' ? c.clone().negate() : new THREE.Vector3(-c.x, -box.min.y, -c.z)
  return transformAll(parts, new THREE.Matrix4().makeTranslation(t.x, t.y, t.z))
}

// ─── Primitivas e importação ─────────────────────────────────────────────────

/** Converte uma BufferGeometry do Three.js (indexada ou não) em Part. */
export function partFromGeometry(geom: THREE.BufferGeometry, nome: string, rgb: RGB | null, escala = 1): Part {
  const posAttr = geom.getAttribute('position') as THREE.BufferAttribute
  const src = posAttr.array as ArrayLike<number>
  const n = posAttr.count
  const idxSrc = geom.getIndex()
  const idxArr: number[] = idxSrc ? Array.from(idxSrc.array as ArrayLike<number>) : Array.from({ length: n }, (_, i) => i)
  const posArr: number[] = new Array(n * 3)
  for (let i = 0; i < n * 3; i++) posArr[i] = src[i] * escala
  const colArr: number[] | undefined = rgb ? new Array(n * 3) : undefined
  if (colArr && rgb) for (let i = 0; i < n * 3; i += 3) { colArr[i] = rgb[0]; colArr[i + 1] = rgb[1]; colArr[i + 2] = rgb[2] }
  const dd = dedup({ pos: posArr, col: colArr ?? [], idx: idxArr })
  return {
    id: novoId(),
    nome,
    pos: new Float32Array(dd.pos),
    col: dd.col.length ? new Float32Array(dd.col) : null,
    idx: new Uint32Array(dd.idx),
    matrix: [...IDENTITY],
    visible: true,
    marker: false,
  }
}

/** Caixa centrada na origem; dimensões em metros. */
export function makeBox(w: number, h: number, d: number, rgb: RGB): Part {
  const g = new THREE.BoxGeometry(w, h, d)
  const p = partFromGeometry(g, 'Caixa', rgb)
  g.dispose()
  return p
}

/** Cilindro com eixo em Y, centrado na origem; diâmetro e comprimento em metros. */
export function makeCylinder(diametro: number, comprimento: number, rgb: RGB, segmentos = 32): Part {
  const g = new THREE.CylinderGeometry(diametro / 2, diametro / 2, comprimento, segmentos, 1, false)
  const p = partFromGeometry(g, 'Cilindro', rgb)
  g.dispose()
  return p
}

/** Tubo (cilindro oco) com eixo em Y; diâmetros externo/interno e comprimento em metros. */
export function makeTube(dExt: number, dInt: number, comprimento: number, rgb: RGB, segmentos = 32): Part {
  const shape = new THREE.Shape()
  shape.absarc(0, 0, dExt / 2, 0, Math.PI * 2, false)
  const hole = new THREE.Path()
  hole.absarc(0, 0, Math.max(0.0005, dInt / 2), 0, Math.PI * 2, true)
  shape.holes.push(hole)
  const g = new THREE.ExtrudeGeometry(shape, { depth: comprimento, bevelEnabled: false, curveSegments: segmentos })
  // extrude sai em Z; gira para Y e centra
  g.rotateX(-Math.PI / 2)
  g.translate(0, -comprimento / 2, 0)
  const p = partFromGeometry(g, 'Tubo', rgb)
  g.dispose()
  return p
}

// ─── Bake e dedup ────────────────────────────────────────────────────────────

const _f32ab = new ArrayBuffer(4)
const _f32view = new DataView(_f32ab)
function f32bits(v: number): number {
  _f32view.setFloat32(0, v, true)
  return _f32view.getUint32(0, true)
}

/**
 * Deduplicação de vértices com quantização float32 — o MESMO algoritmo do
 * parse-worker.ts (e do www/apps/ingestao/pipeline/dedup.py). A chave inclui a cor, então vértices
 * de cores diferentes não se fundem — e é isso que permite re-segmentar depois.
 */
export function dedup(g: { pos: number[]; col: number[]; idx: number[] }): { pos: number[]; col: number[]; idx: number[] } {
  const { pos, col, idx } = g
  const hasCol = col.length > 0
  const seen = new Map<string, number>()
  const newPos: number[] = []
  const newCol: number[] = []
  const newIdx: number[] = []
  for (const vi of idx) {
    const px = pos[vi * 3], py = pos[vi * 3 + 1], pz = pos[vi * 3 + 2]
    let key: string
    if (hasCol) {
      key = `${f32bits(px)},${f32bits(py)},${f32bits(pz)},${f32bits(col[vi * 3])},${f32bits(col[vi * 3 + 1])},${f32bits(col[vi * 3 + 2])}`
    } else {
      key = `${f32bits(px)},${f32bits(py)},${f32bits(pz)}`
    }
    let ni = seen.get(key)
    if (ni === undefined) {
      ni = newPos.length / 3
      seen.set(key, ni)
      newPos.push(px, py, pz)
      if (hasCol) newCol.push(col[vi * 3], col[vi * 3 + 1], col[vi * 3 + 2])
    }
    newIdx.push(ni)
  }
  return { pos: newPos, col: newCol, idx: newIdx }
}

/**
 * Aplica as matrizes, concatena as partes visíveis e deduplica.
 * Partes invisíveis NÃO entram — ocultar e salvar é a forma de excluir.
 * Se nenhuma parte tem cor, `col` sai vazio (o viewer usa o cinza padrão).
 */
export function bake(parts: Part[]): GeoData & { idx: number[] } {
  const vis = parts.filter((p) => p.visible)
  const anyCol = vis.some((p) => p.col)
  const pos: number[] = []
  const col: number[] = []
  const idx: number[] = []
  for (const p0 of vis) {
    const p = bakeMatrix(p0)
    const base = pos.length / 3
    for (let i = 0; i < p.pos.length; i++) pos.push(p.pos[i])
    if (anyCol) {
      if (p.col) for (let i = 0; i < p.col.length; i++) col.push(p.col[i])
      else for (let i = 0; i < p.pos.length; i += 3) col.push(0.533, 0.588, 0.667)
    }
    for (let i = 0; i < p.idx.length; i++) idx.push(p.idx[i] + base)
  }
  // arredonda a 6 casas: o JSON fica ~40% menor e a precisão (1 µm) é maior que a do float32 do viewer
  const r6 = (v: number) => Math.round(v * 1e6) / 1e6
  const dd = dedup({ pos: pos.map(r6), col: col.map((v) => Math.round(v * 1e4) / 1e4), idx })
  return dd
}

// ─── Cores utilitárias ───────────────────────────────────────────────────────

export function rgbToHex(rgb: RGB): string {
  const h = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')
  return `#${h(rgb[0])}${h(rgb[1])}${h(rgb[2])}`
}

export function hexToRgb(hex: string): RGB {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  if (!m) return [0.533, 0.588, 0.667]
  return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255]
}

export const COR_PADRAO: RGB = [0.533, 0.588, 0.667]

/** Formata metros como centímetros com 2 casas — a unidade nativa do AltoQi. */
export function cm(m: number): string {
  return (m * 100).toFixed(2)
}
