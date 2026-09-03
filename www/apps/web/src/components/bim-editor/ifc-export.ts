/**
 * ifc-export.ts — escreve o modelo editado como IFC4 (STEP / ISO-10303-21).
 *
 * É o caminho inverso do `scripts/parse_ifc.py` e da skill `leitor-ifc`, e segue
 * a estrutura que o exportador do AltoQi produz para a Dancor — a que aquele parser
 * já sabe ler:
 *
 *   IFCPROJECT → IFCSITE → IFCBUILDING → IFCBUILDINGSTOREY
 *     └─ IFCELEMENTASSEMBLY (o produto; SEM Representation própria)
 *          └─ IFCRELAGGREGATES → IFCBUILDINGELEMENTPROXY (uma por parte do editor)
 *               ├─ ObjectPlacement  → IFCLOCALPLACEMENT → IFCAXIS2PLACEMENT3D
 *               └─ Representation   → IFCPRODUCTDEFINITIONSHAPE
 *                    → IFCSHAPEREPRESENTATION('Body','Tessellation')
 *                      → IFCTRIANGULATEDFACESET ← IFCINDEXEDCOLOURMAP (cor por face)
 *                                               ← IFCSTYLEDITEM (cor para viewers que ignoram o mapa)
 *
 * Decisões que vêm direto das armadilhas documentadas:
 *
 * - **Uma entidade por linha.** `build_entity_index` do parser casa `#id=TIPO(args);`
 *   por linha; um face set quebrado em várias linhas seria descartado em silêncio.
 * - **A montagem não tem Representation.** O parser processa IFCELEMENTASSEMBLY *e*
 *   IFCBUILDINGELEMENTPROXY; geometria nos dois contaria em dobro.
 * - **Unidade METRE com valores em metros.** O parser não converte unidade — só troca
 *   eixos. Declarar MILLIMETRE e escrever metros (como faz o CATIA) é a armadilha
 *   que a skill manda verificar; aqui declaração e valores são coerentes.
 * - **Eixos: Three.js (Y-up) → IFC (Z-up)** é o inverso do `ifc_to_threejs`:
 *   `ifc = (x, −z, y)`.
 * - **Transformação rígida vira IFCLOCALPLACEMENT; escala é assada nos vértices.**
 *   IFCAXIS2PLACEMENT3D só expressa rotação+translação. Quando a matriz da parte é
 *   ortonormal com det>0, ela vai como placement (Axis = coluna Z, RefDirection =
 *   coluna X, como o `axis2placement_mat` do parser reconstrói via Gram-Schmidt); caso
 *   contrário os vértices saem já em coordenadas de mundo e o placement é identidade.
 * - **REAL sempre com ponto** (`1.`, não `1`), sem expoente — `parse_floats` e a regex
 *   do IFCCOLOURRGBLIST (`[0-9.,\s]+`) não aceitam `1e-7`.
 * - **`ColourIndex` é 1-based, um por triângulo**, igual em tamanho ao CoordIndex.
 * - **`Closed`** é `.T.` só quando a parte não tem aresta de borda (partStats).
 * - **Strings STEP**: apóstrofo dobrado, não-ASCII em `\X2\…\X0\`.
 *
 * As informações do produto (nome, série, specs, potência, conexões) vão em dois
 * IFCPROPERTYSET ligados à montagem — assim o IFC carrega o mesmo que o Mongo.
 */

import * as THREE from 'three'
import { bakeMatrix, partStats, type Part, type RGB } from './mesh-model'

export interface IfcExportInfo {
  nome: string
  /** slug do produto no .aq (vai em Tag) */
  id: string
  serie?: string | null
  fabricante?: string | null
  catalogo?: string | null
  specs?: Record<string, string> | null
  potencia?: number | null
  conexoes?: string | null
  /** id do produto no Mongo, para rastrear a origem */
  produtoId?: string
}

export interface IfcExportOptions {
  /** inclui partes marcadas como bocal de conexão (padrão: não — são marcadores, não produto) */
  incluirBocais?: boolean
  /** inclui partes ocultas (padrão: não — oculto e salvo é excluído) */
  incluirOcultas?: boolean
  /** nome do arquivo gravado no cabeçalho */
  fileName?: string
}

export interface IfcExportResult {
  ifc: string
  partes: number
  triangulos: number
  vertices: number
  bytes: number
}

// ─── STEP: formatação ────────────────────────────────────────────────────────

/** REAL do STEP: sempre com ponto decimal, nunca em notação científica. */
export function real(v: number, dec = 6): string {
  if (!Number.isFinite(v)) v = 0
  let s = (Math.round(v * 10 ** dec) / 10 ** dec).toString()
  if (/e/i.test(s)) s = v.toFixed(dec)
  if (s === '-0') s = '0'
  if (!s.includes('.')) s += '.'
  return s
}

/** STRING do STEP: apóstrofo dobrado; fora do ASCII imprimível vai em \X2\…\X0\. */
export function str(s: string | null | undefined): string {
  if (s == null) return '$'
  let out = ''
  let uni = ''
  const flush = () => {
    if (uni) {
      out += `\\X2\\${uni}\\X0\\`
      uni = ''
    }
  }
  for (const ch of s) {
    const cp = ch.codePointAt(0)!
    if (cp >= 0x20 && cp < 0x7f) {
      flush()
      out += ch === "'" ? "''" : ch === '\\' ? '\\\\' : ch
    } else if (cp <= 0xffff) {
      uni += cp.toString(16).toUpperCase().padStart(4, '0')
    } else {
      // fora do BMP: \X4\ com 8 dígitos — raro em nome de peça; simplifica para '?'
      flush()
      out += '?'
    }
  }
  flush()
  return `'${out}'`
}

/**
 * GlobalId do IFC: UUID de 128 bits em 22 caracteres base-64 (alfabeto próprio).
 * Algoritmo canônico: 2 hex → 2 chars, depois 5 grupos de 6 hex → 4 chars cada.
 */
const B64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'
export function ifcGuid(uuid?: string): string {
  const hex = (uuid ?? crypto.randomUUID()).replace(/-/g, '')
  if (hex.length !== 32) throw new Error('uuid inválido')
  const enc = (h: string, n: number) => {
    let v = parseInt(h, 16)
    let s = ''
    for (let i = 0; i < n; i++) {
      s = B64[v & 63] + s
      v = Math.floor(v / 64)
    }
    return s
  }
  return enc(hex.slice(0, 2), 2) + [2, 8, 14, 20, 26].map((i) => enc(hex.slice(i, i + 6), 4)).join('')
}

// ─── Eixos e placement ───────────────────────────────────────────────────────

/** Three.js (Y-up) → IFC (Z-up): (x, y, z) → (x, −z, y). Inverso de ifc_to_threejs. */
function toIfc(x: number, y: number, z: number): [number, number, number] {
  return [x, -z, y]
}

const EPS = 1e-6

/**
 * Se a matriz é rígida (rotação própria + translação), devolve os vetores do
 * IFCAXIS2PLACEMENT3D já em coordenadas IFC; senão null (a parte será assada).
 */
function rigidPlacement(m: number[]): { loc: [number, number, number]; axis: [number, number, number]; ref: [number, number, number] } | null {
  const M = new THREE.Matrix4().fromArray(m)
  const e = M.elements // column-major
  const cx = new THREE.Vector3(e[0], e[1], e[2])
  const cy = new THREE.Vector3(e[4], e[5], e[6])
  const cz = new THREE.Vector3(e[8], e[9], e[10])
  if (Math.abs(e[3]) > EPS || Math.abs(e[7]) > EPS || Math.abs(e[11]) > EPS || Math.abs(e[15] - 1) > EPS) return null
  if (Math.abs(cx.length() - 1) > EPS || Math.abs(cy.length() - 1) > EPS || Math.abs(cz.length() - 1) > EPS) return null
  if (Math.abs(cx.dot(cy)) > EPS || Math.abs(cy.dot(cz)) > EPS || Math.abs(cz.dot(cx)) > EPS) return null
  if (M.determinant() < 0) return null
  // R_ifc = C · R · Cᵀ, com C: (x,y,z) → (x,−z,y). Coluna k de R_ifc = C · R · (Cᵀ e_k).
  // Cᵀ e_x = e_x ; Cᵀ e_z(ifc) = e_y(three). Logo: RefDirection = C·cx, Axis = C·cy.
  const axis = toIfc(cy.x, cy.y, cy.z)
  const ref = toIfc(cx.x, cx.y, cx.z)
  const loc = toIfc(e[12], e[13], e[14])
  return { loc, axis, ref }
}

// ─── Exportador ──────────────────────────────────────────────────────────────

export function exportIfc(parts: Part[], info: IfcExportInfo, opts: IfcExportOptions = {}): IfcExportResult {
  const lines: string[] = []
  let n = 0
  const add = (body: string): number => {
    n += 1
    lines.push(`#${n}=${body};`)
    return n
  }
  const ref = (id: number) => `#${id}`
  const list = (ids: number[]) => `(${ids.map(ref).join(',')})`

  const selecionadas = parts.filter((p) => (opts.incluirOcultas || p.visible) && (opts.incluirBocais || !p.marker))

  // ── contexto, unidades, projeto ──
  const origin = add('IFCCARTESIANPOINT((0.,0.,0.))')
  const dirZ = add('IFCDIRECTION((0.,0.,1.))')
  const dirX = add('IFCDIRECTION((1.,0.,0.))')
  const worldAxis = add(`IFCAXIS2PLACEMENT3D(${ref(origin)},${ref(dirZ)},${ref(dirX)})`)
  const ctx = add(`IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,0.00001,${ref(worldAxis)},$)`)
  const bodyCtx = add(`IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,${ref(ctx)},$,.MODEL_VIEW.,$)`)
  const uLen = add('IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)')
  const uArea = add('IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)')
  const uVol = add('IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)')
  const uAng = add('IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)')
  const units = add(`IFCUNITASSIGNMENT(${list([uLen, uArea, uVol, uAng])})`)
  const projeto = add(`IFCPROJECT('${ifcGuid()}',$,${str(info.catalogo ?? info.nome)},${str(info.fabricante ? `Biblioteca BIM ${info.fabricante}` : null)},$,$,$,(${ref(ctx)}),${ref(units)})`)

  // ── estrutura espacial mínima ──
  const siteLP = add(`IFCLOCALPLACEMENT($,${ref(worldAxis)})`)
  const site = add(`IFCSITE('${ifcGuid()}',$,'Site',$,$,${ref(siteLP)},$,$,.ELEMENT.,$,$,$,$,$)`)
  add(`IFCRELAGGREGATES('${ifcGuid()}',$,$,$,${ref(projeto)},(${ref(site)}))`)
  const bldLP = add(`IFCLOCALPLACEMENT(${ref(siteLP)},${ref(worldAxis)})`)
  const bld = add(`IFCBUILDING('${ifcGuid()}',$,'Building',$,$,${ref(bldLP)},$,$,.ELEMENT.,$,$,$)`)
  add(`IFCRELAGGREGATES('${ifcGuid()}',$,$,$,${ref(site)},(${ref(bld)}))`)
  const stoLP = add(`IFCLOCALPLACEMENT(${ref(bldLP)},${ref(worldAxis)})`)
  const sto = add(`IFCBUILDINGSTOREY('${ifcGuid()}',$,'Storey',$,$,${ref(stoLP)},$,$,.ELEMENT.,0.)`)
  add(`IFCRELAGGREGATES('${ifcGuid()}',$,$,$,${ref(bld)},(${ref(sto)}))`)

  // ── a montagem (o produto) — sem Representation: quem tem geometria são as partes ──
  const asmLP = add(`IFCLOCALPLACEMENT(${ref(stoLP)},${ref(worldAxis)})`)
  const asm = add(
    `IFCELEMENTASSEMBLY('${ifcGuid()}',$,${str(info.nome)},${str(info.serie ? `Série ${info.serie}` : null)},$,${ref(asmLP)},$,${str(info.id)},.NOTDEFINED.,.NOTDEFINED.)`,
  )
  add(`IFCRELCONTAINEDINSPATIALSTRUCTURE('${ifcGuid()}',$,$,$,(${ref(asm)}),${ref(sto)})`)

  // ── partes ──
  const proxies: number[] = []
  let tris = 0, verts = 0
  for (const part of selecionadas) {
    const rigid = rigidPlacement(part.matrix)
    const src = rigid ? part : bakeMatrix(part) // sem placement rígido, assa a matriz

    // placement da parte
    let axisId = worldAxis
    if (rigid) {
      const loc = add(`IFCCARTESIANPOINT((${rigid.loc.map((v) => real(v)).join(',')}))`)
      const ax = add(`IFCDIRECTION((${rigid.axis.map((v) => real(v, 9)).join(',')}))`)
      const rd = add(`IFCDIRECTION((${rigid.ref.map((v) => real(v, 9)).join(',')}))`)
      axisId = add(`IFCAXIS2PLACEMENT3D(${ref(loc)},${ref(ax)},${ref(rd)})`)
    }
    const lp = add(`IFCLOCALPLACEMENT(${ref(asmLP)},${ref(axisId)})`)

    // pontos (Y-up → Z-up)
    const nV = src.pos.length / 3
    const pts: string[] = new Array(nV)
    for (let i = 0; i < nV; i++) {
      const [x, y, z] = toIfc(src.pos[i * 3], src.pos[i * 3 + 1], src.pos[i * 3 + 2])
      pts[i] = `(${real(x)},${real(y)},${real(z)})`
    }
    const pl = add(`IFCCARTESIANPOINTLIST3D((${pts.join(',')}))`)

    // triângulos (1-based)
    const nT = src.idx.length / 3
    const tri: string[] = new Array(nT)
    for (let t = 0; t < nT; t++) {
      tri[t] = `(${src.idx[t * 3] + 1},${src.idx[t * 3 + 1] + 1},${src.idx[t * 3 + 2] + 1})`
    }
    const stats = partStats(src)
    const closed = stats.arestasBorda === 0 && stats.arestasNaoManifold === 0 && nT > 0 ? '.T.' : '.F.'
    const fs = add(`IFCTRIANGULATEDFACESET(${ref(pl)},$,${closed},(${tri.join(',')}),$)`)

    // cor por face: paleta de cores distintas + índice 1-based por triângulo
    let dominante: RGB | null = null
    if (src.col) {
      const palette: string[] = []
      const paletteIdx = new Map<string, number>()
      const colourIndex: number[] = new Array(nT)
      for (let t = 0; t < nT; t++) {
        const v = src.idx[t * 3]
        const key = `${real(src.col[v * 3], 4)},${real(src.col[v * 3 + 1], 4)},${real(src.col[v * 3 + 2], 4)}`
        let k = paletteIdx.get(key)
        if (k === undefined) {
          k = palette.length + 1
          paletteIdx.set(key, k)
          palette.push(key)
        }
        colourIndex[t] = k
      }
      const rgbList = add(`IFCCOLOURRGBLIST((${palette.map((c) => `(${c})`).join(',')}))`)
      add(`IFCINDEXEDCOLOURMAP(${ref(fs)},1.,${ref(rgbList)},(${colourIndex.join(',')}))`)
      dominante = [src.col[0], src.col[1], src.col[2]]
    }
    // estilo de superfície — para viewers que ignoram IFCINDEXEDCOLOURMAP
    if (dominante) {
      const rgb = add(`IFCCOLOURRGB($,${real(dominante[0], 4)},${real(dominante[1], 4)},${real(dominante[2], 4)})`)
      const rend = add(`IFCSURFACESTYLERENDERING(${ref(rgb)},0.,$,$,$,$,$,$,.NOTDEFINED.)`)
      const style = add(`IFCSURFACESTYLE($,.BOTH.,(${ref(rend)}))`)
      add(`IFCSTYLEDITEM(${ref(fs)},(${ref(style)}),$)`)
    }

    const sr = add(`IFCSHAPEREPRESENTATION(${ref(bodyCtx)},'Body','Tessellation',(${ref(fs)}))`)
    const pds = add(`IFCPRODUCTDEFINITIONSHAPE($,$,(${ref(sr)}))`)
    const proxy = add(
      `IFCBUILDINGELEMENTPROXY('${ifcGuid()}',$,${str(part.nome)},${str(part.marker ? 'Bocal de conexão (marcador AltoQi)' : null)},$,${ref(lp)},${ref(pds)},$,.NOTDEFINED.)`,
    )
    proxies.push(proxy)
    tris += nT
    verts += nV
  }
  if (proxies.length) add(`IFCRELAGGREGATES('${ifcGuid()}',$,'Partes',$,${ref(asm)},${list(proxies)})`)

  // ── propriedades: o que está no Mongo viaja junto ──
  const prop = (nome: string, valor: string | number | null | undefined, tipo: 'IFCLABEL' | 'IFCTEXT' | 'IFCREAL' = 'IFCLABEL') => {
    if (valor == null || valor === '') return null
    const val = tipo === 'IFCREAL' ? `IFCREAL(${real(Number(valor), 4)})` : `${tipo}(${str(String(valor))})`
    return add(`IFCPROPERTYSINGLEVALUE(${str(nome)},$,${val},$)`)
  }
  const produtoProps = [
    prop('Nome', info.nome),
    prop('Id', info.id),
    prop('Serie', info.serie),
    prop('Fabricante', info.fabricante),
    prop('Catalogo', info.catalogo),
    prop('Potencia_cv', info.potencia, 'IFCREAL'),
    prop('Conexoes', info.conexoes),
    prop('Origem', info.produtoId ? `bilds-bim-3d poc-edicao · produto ${info.produtoId}` : 'bilds-bim-3d poc-edicao'),
  ].filter((x): x is number => x !== null)
  if (produtoProps.length) {
    const pset = add(`IFCPROPERTYSET('${ifcGuid()}',$,'bilds_Produto',$,${list(produtoProps)})`)
    add(`IFCRELDEFINESBYPROPERTIES('${ifcGuid()}',$,$,$,(${ref(asm)}),${ref(pset)})`)
  }
  const specProps = Object.entries(info.specs ?? {})
    .map(([k, v]) => prop(k, v, 'IFCTEXT'))
    .filter((x): x is number => x !== null)
  if (specProps.length) {
    const pset = add(`IFCPROPERTYSET('${ifcGuid()}',$,'bilds_Especificacoes',$,${list(specProps)})`)
    add(`IFCRELDEFINESBYPROPERTIES('${ifcGuid()}',$,$,$,(${ref(asm)}),${ref(pset)})`)
  }

  // ── arquivo ──
  const ts = new Date().toISOString().slice(0, 19)
  const fileName = opts.fileName ?? `${info.id}.ifc`
  const header = [
    'ISO-10303-21;',
    'HEADER;',
    "FILE_DESCRIPTION(('ViewDefinition [ReferenceView_V1.2]'),'2;1');",
    `FILE_NAME(${str(fileName)},'${ts}',('bilds'),('bilds.com'),'bilds-bim-3d poc-edicao','bilds-bim-3d editor 3D','');`,
    "FILE_SCHEMA(('IFC4'));",
    'ENDSEC;',
    'DATA;',
  ]
  const ifc = [...header, ...lines, 'ENDSEC;', 'END-ISO-10303-21;', ''].join('\n')
  return { ifc, partes: selecionadas.length, triangulos: tris, vertices: verts, bytes: ifc.length }
}
