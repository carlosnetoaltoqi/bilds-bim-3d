'use client'

/**
 * GeometryPanel — o painel de ferramentas do editor 3D.
 *
 * Toda operação sobre a malha passa por `onUpdate(novasPartes, rótulo)`, que o
 * ProductEditor grava no histórico (undo/redo). O painel não guarda estado de
 * geometria: só formulários locais (dimensões de primitiva, arquivo a importar).
 */

import { useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import {
  COR_PADRAO,
  bakeMatrix,
  cm,
  docBbox,
  flipNormals,
  hexToRgb,
  makeBox,
  makeCylinder,
  makeTube,
  mergeParts,
  mirror,
  novoId,
  partFromGeometry,
  partStats,
  recenter,
  recolor,
  rgbToHex,
  segment,
  transformAll,
  bake,
  withMatrix,
  type Part,
  type RGB,
} from './mesh-model'
import type { Tool, ViewPreset } from './EditorViewport'
import { Field, btnPrimary, btnSmall, inputCls } from './InfoForm'

export interface EditorUi {
  tool: Tool
  wireframe: boolean
  snap: boolean
  showGrid: boolean
  showMarkers: boolean
  clipEnabled: boolean
  clipFrac: number
  ghostOn: boolean
}

export interface GeometryPanelProps {
  parts: Part[]
  selected: string[]
  onSelect: (ids: string[], additive: boolean) => void
  onUpdate: (next: Part[], label: string) => void
  ui: EditorUi
  setUi: (patch: Partial<EditorUi>) => void
  onFit: () => void
  onView: (v: ViewPreset) => void
  history: { canUndo: boolean; canRedo: boolean; undo: () => void; redo: () => void; lastLabel: string | null }
  geoState: {
    dirty: boolean
    saving: boolean
    msg: { tipo: 'ok' | 'erro' | 'info'; texto: string } | null
    geoEditadoEm: string | null
    save: () => void
    restore: () => void
    download: () => void
    reload: () => void
    /** gera e baixa o IFC4 do estado atual do editor (não grava no storage) */
    exportIfc: (opts: { incluirBocais: boolean }) => void
    /** grava o JSON no storage e em seguida baixa o IFC */
    saveAndExportIfc: (opts: { incluirBocais: boolean }) => void
    /** gera um .aq (AltoQi) com as partes visíveis, via API + eng-reversa, e baixa */
    exportAq: (opts: { incluirBocais: boolean }) => void
  }
}

const TOOLS: Array<{ id: Tool; label: string; tecla: string }> = [
  { id: 'select', label: 'Selecionar', tecla: '1' },
  { id: 'translate', label: 'Mover', tecla: '2' },
  { id: 'rotate', label: 'Girar', tecla: '3' },
  { id: 'scale', label: 'Escalar', tecla: '4' },
]

export function GeometryPanel(p: GeometryPanelProps) {
  const { parts, selected, ui, setUi } = p
  const selSet = useMemo(() => new Set(selected), [selected])
  const primary = selected.length ? parts.find((x) => x.id === selected[selected.length - 1]) ?? null : null
  const selParts = parts.filter((x) => selSet.has(x.id))

  // estatísticas: só das partes selecionadas (custo proporcional) + totais baratos
  const primaryStats = useMemo(() => (primary ? partStats(primary) : null), [primary])
  const totals = useMemo(() => {
    let tris = 0, verts = 0, vis = 0
    for (const x of parts) {
      if (!x.visible) continue
      vis++
      tris += x.idx.length / 3
      verts += x.pos.length / 3
    }
    return { tris, verts, vis, bbox: docBbox(parts) }
  }, [parts])
  const partsComBorda = useMemo(() => {
    // conta arestas de borda de todas as partes só quando são poucas (< 300 partes) — senão fica caro a cada render
    if (parts.length > 300) return null
    const m = new Map<string, number>()
    for (const x of parts) m.set(x.id, partStats(x).arestasBorda)
    return m
  }, [parts])

  // ── helpers de edição ────────────────────────────────────────────────────
  const replace = (fn: (x: Part) => Part, label: string, ids: Set<string> = selSet) =>
    p.onUpdate(parts.map((x) => (ids.has(x.id) ? fn(x) : x)), label)

  function excluir() {
    p.onUpdate(parts.filter((x) => !selSet.has(x.id)), `excluir ${selected.length} parte(s)`)
    p.onSelect([], false)
  }
  function duplicar() {
    const box = docBbox(selParts)
    const dx = box.isEmpty() ? 0.05 : (box.max.x - box.min.x) * 1.1 + 0.005
    const novas = selParts.map((x) => {
      const m = new THREE.Matrix4().fromArray(x.matrix).premultiply(new THREE.Matrix4().makeTranslation(dx, 0, 0))
      return { ...x, id: novoId(), nome: `${x.nome} (cópia)`, matrix: m.toArray() }
    })
    p.onUpdate([...parts, ...novas], 'duplicar')
    p.onSelect(novas.map((x) => x.id), false)
  }
  function fundir() {
    if (selParts.length < 2) return
    const fused = mergeParts(selParts)
    const idxFirst = parts.findIndex((x) => selSet.has(x.id))
    const rest = parts.filter((x) => !selSet.has(x.id))
    rest.splice(idxFirst, 0, fused)
    p.onUpdate(rest, `fundir ${selParts.length} partes`)
    p.onSelect([fused.id], false)
  }
  function resegmentar() {
    const geo = bake(parts)
    const novas = segment(geo)
    p.onUpdate(novas, 're-segmentar')
    p.onSelect([], false)
  }
  function removerBocais() {
    const n = parts.filter((x) => x.marker).length
    if (!n) return
    p.onUpdate(parts.filter((x) => !x.marker), `remover ${n} bocal(is)`)
    p.onSelect([], false)
  }
  function girarGlobal(eixo: 'x' | 'y' | 'z', graus: number) {
    const r = THREE.MathUtils.degToRad(graus)
    const m = eixo === 'x' ? new THREE.Matrix4().makeRotationX(r) : eixo === 'y' ? new THREE.Matrix4().makeRotationY(r) : new THREE.Matrix4().makeRotationZ(r)
    p.onUpdate(transformAll(parts, m), `girar ${graus}° em ${eixo.toUpperCase()}`)
  }
  function escalaGlobal(f: number) {
    if (!Number.isFinite(f) || f <= 0) return
    p.onUpdate(transformAll(parts, new THREE.Matrix4().makeScale(f, f, f)), `escala ×${f}`)
  }

  // ── transformação numérica da parte principal ────────────────────────────
  const trs = useMemo(() => {
    if (!primary) return null
    const m = new THREE.Matrix4().fromArray(primary.matrix)
    const pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3()
    m.decompose(pos, q, sc)
    const e = new THREE.Euler().setFromQuaternion(q, 'XYZ')
    return { pos, rot: [e.x, e.y, e.z].map((r) => THREE.MathUtils.radToDeg(r)), sc }
  }, [primary])

  function setTrs(kind: 'pos' | 'rot' | 'sc', k: 0 | 1 | 2, valor: number) {
    if (!primary || !trs || !Number.isFinite(valor)) return
    const pos = trs.pos.clone(), rot = [...trs.rot], sc = trs.sc.clone()
    if (kind === 'pos') pos.setComponent(k, valor / 100)
    if (kind === 'rot') rot[k] = valor
    if (kind === 'sc') sc.setComponent(k, valor)
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(...(rot.map((d) => THREE.MathUtils.degToRad(d)) as [number, number, number]), 'XYZ'))
    const m = new THREE.Matrix4().compose(pos, q, sc)
    replace((x) => withMatrix(x, m.toArray()), 'transformar', new Set([primary.id]))
  }

  // ── primitivas / importação ──────────────────────────────────────────────
  const [prim, setPrim] = useState({ tipo: 'cilindro' as 'caixa' | 'cilindro' | 'tubo', a: 5, b: 5, c: 10, cor: '#8896aa' })
  const [unidade, setUnidade] = useState<'mm' | 'cm' | 'm'>('mm')
  const [ifcBocais, setIfcBocais] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  function adicionarPrimitiva() {
    const rgb = hexToRgb(prim.cor)
    const a = prim.a / 100, b = prim.b / 100, c = prim.c / 100
    let nova: Part
    if (prim.tipo === 'caixa') nova = makeBox(a, b, c, rgb)
    else if (prim.tipo === 'cilindro') nova = makeCylinder(a, c, rgb)
    else nova = makeTube(a, b, c, rgb)
    // nasce sobre o topo do modelo, para não nascer dentro dele
    const box = docBbox(parts)
    if (!box.isEmpty()) {
      const own = docBbox([nova])
      nova = withMatrix(nova, new THREE.Matrix4().makeTranslation(0, box.max.y - own.min.y + 0.01, 0).toArray())
    }
    p.onUpdate([...parts, nova], `adicionar ${nova.nome.toLowerCase()}`)
    p.onSelect([nova.id], false)
  }

  async function importarArquivo(file: File) {
    const escala = unidade === 'mm' ? 0.001 : unidade === 'cm' ? 0.01 : 1
    const ext = file.name.toLowerCase().split('.').pop()
    if (ext === 'stp' || ext === 'step' || ext === 'ifc') {
      // STEP/IFC não entram mais pelo editor (2026-09-05): a conversão é do serviço de ingestão e
      // a peça vira um produto pela página inicial → "Importar peça STEP / IFC"
      alert('STEP e IFC entram pela página inicial (Importar peça STEP / IFC), como um produto novo. Aqui só STL, OBJ e JSON.')
      return
    }
    const novas: Part[] = []
    try {
      if (ext === 'stl') {
        const g = new STLLoader().parse(await file.arrayBuffer())
        novas.push(partFromGeometry(g, file.name, COR_PADRAO, escala))
        g.dispose()
      } else if (ext === 'obj') {
        const grp = new OBJLoader().parse(await file.text())
        grp.traverse((o) => {
          const mesh = o as THREE.Mesh
          if (mesh.isMesh) novas.push(partFromGeometry(mesh.geometry as THREE.BufferGeometry, mesh.name || file.name, COR_PADRAO, escala))
        })
      } else if (ext === 'json') {
        const data = JSON.parse(await file.text())
        if (!Array.isArray(data.pos)) throw new Error('JSON sem "pos" — esperado { pos, col, idx }')
        const geo = { pos: (data.pos as number[]).map((v) => v * escala), col: data.col ?? [], idx: data.idx }
        for (const x of segment(geo)) novas.push({ ...x, nome: `${file.name} · ${x.nome}` })
      } else {
        throw new Error('formato não suportado — use STL, OBJ ou JSON { pos, col, idx }')
      }
    } catch (e: any) {
      alert(`Falha ao importar: ${e.message ?? e}`)
      return
    }
    if (!novas.length) return
    p.onUpdate([...parts, ...novas], `importar ${file.name}`)
    p.onSelect(novas.map((x) => x.id), false)
  }

  const bb = totals.bbox
  const size = bb.isEmpty() ? null : bb.getSize(new THREE.Vector3())

  return (
    <div className="flex flex-col gap-4 text-[13px]">
      {/* ── ferramentas ── */}
      <Section title="Ferramenta">
        <div className="flex flex-wrap gap-1">
          {TOOLS.map((t) => (
            <button key={t.id} type="button" onClick={() => setUi({ tool: t.id })} title={`tecla ${t.tecla}`}
              className={`${btnSmall} ${ui.tool === t.id ? '!bg-[#1e40af] !text-white !border-[#1e40af]' : ''}`}>{t.label}</button>
          ))}
          <span className="w-px bg-gray-200 mx-1" />
          <button type="button" onClick={p.history.undo} disabled={!p.history.canUndo} className={btnSmall} title="Ctrl+Z">↶ desfazer</button>
          <button type="button" onClick={p.history.redo} disabled={!p.history.canRedo} className={btnSmall} title="Ctrl+Shift+Z">↷ refazer</button>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[12px] text-gray-700">
          <Check label="snap 5 mm / 15°" checked={ui.snap} onChange={(v) => setUi({ snap: v })} />
          <Check label="wireframe" checked={ui.wireframe} onChange={(v) => setUi({ wireframe: v })} />
          <Check label="grade" checked={ui.showGrid} onChange={(v) => setUi({ showGrid: v })} />
          <Check label="bocais" checked={ui.showMarkers} onChange={(v) => setUi({ showMarkers: v })} />
          <Check label="fantasma do original" checked={ui.ghostOn} onChange={(v) => setUi({ ghostOn: v })} />
        </div>
        <div className="flex items-center gap-2 mt-2">
          <Check label="corte em Y" checked={ui.clipEnabled} onChange={(v) => setUi({ clipEnabled: v })} />
          <input type="range" min={0} max={1} step={0.005} value={ui.clipFrac} disabled={!ui.clipEnabled}
            onChange={(e) => setUi({ clipFrac: Number(e.target.value) })} className="flex-1" />
          <span className="text-[11px] text-gray-500 w-10 text-right">{Math.round(ui.clipFrac * 100)}%</span>
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {(['iso', 'frente', 'topo', 'direita', 'esquerda', 'tras', 'baixo'] as ViewPreset[]).map((v) => (
            <button key={v} type="button" onClick={() => p.onView(v)} className={btnSmall}>{v}</button>
          ))}
          <button type="button" onClick={p.onFit} className={btnSmall} title="tecla F">enquadrar</button>
        </div>
      </Section>

      {/* ── partes ── */}
      <Section title={`Partes (${parts.length})`} right={
        <span className="flex gap-1">
          <button type="button" className={btnSmall} onClick={() => p.onSelect(parts.map((x) => x.id), false)}>todas</button>
          <button type="button" className={btnSmall} onClick={() => p.onSelect([], false)}>nenhuma</button>
        </span>
      }>
        <ul className="max-h-[220px] overflow-y-auto border border-gray-200 rounded divide-y divide-gray-100">
          {parts.map((x) => {
            const sel = selSet.has(x.id)
            const borda = partsComBorda?.get(x.id) ?? 0
            return (
              <li key={x.id}
                onClick={(e) => p.onSelect([x.id], e.shiftKey || e.ctrlKey || e.metaKey)}
                className={`flex items-center gap-2 px-2 py-1 cursor-pointer text-[12px] ${sel ? 'bg-blue-50' : 'hover:bg-gray-50'} ${x.visible ? '' : 'opacity-50'}`}>
                <button type="button" title={x.visible ? 'ocultar' : 'mostrar'}
                  onClick={(e) => { e.stopPropagation(); replace((y) => ({ ...y, visible: !y.visible }), x.visible ? 'ocultar' : 'mostrar', new Set([x.id])) }}
                  className="w-4 text-gray-400 hover:text-gray-800">{x.visible ? '●' : '○'}</button>
                <span className="w-3 h-3 rounded-sm border border-black/10 shrink-0" style={{ background: x.col ? rgbToHex([x.col[0], x.col[1], x.col[2]]) : '#8896aa' }} />
                <span className="flex-1 truncate">{x.nome}</span>
                {x.marker && <span className="text-[10px] px-1 rounded bg-green-100 text-green-800">bocal</span>}
                {borda > 0 && <span className="text-[10px] px-1 rounded bg-amber-100 text-amber-800" title="arestas de borda — malha aberta">{borda} ab.</span>}
                <span className="text-[11px] text-gray-400 tabular-nums">{(x.idx.length / 3).toLocaleString('pt-BR')} △</span>
              </li>
            )
          })}
        </ul>
        <p className="text-[11px] text-gray-500 mt-1">
          {totals.vis} visíveis · {totals.tris.toLocaleString('pt-BR')} triângulos · {totals.verts.toLocaleString('pt-BR')} vértices
          {size && <> · {cm(size.x)} × {cm(size.y)} × {cm(size.z)} cm</>}
        </p>
        <p className="text-[11px] text-gray-400 mt-1">
          <em>ab.</em> = arestas de borda (com um só triângulo). Malha de fabricante costuma vir como sopa de triângulos
          — na Dancor, 25–32% das arestas — então o número só é um alarme em partes geradas ou importadas, que devem dar 0.
        </p>
      </Section>

      {/* ── seleção ── */}
      {primary && trs && primaryStats && (
        <Section title={selected.length > 1 ? `Seleção (${selected.length}) · ${primary.nome}` : primary.nome}>
          <div className="flex items-center gap-2 mb-2">
            <input value={primary.nome} onChange={(e) => replace((y) => ({ ...y, nome: e.target.value }), 'renomear', new Set([primary.id]))} className={inputCls} />
            <input type="color" value={primary.col ? rgbToHex([primary.col[0], primary.col[1], primary.col[2]]) : '#8896aa'}
              onChange={(e) => replace((y) => recolor(y, hexToRgb(e.target.value)), 'recolorir')} title="cor (aplica na seleção)" className="w-9 h-8 p-0 border border-gray-300 rounded cursor-pointer" />
          </div>
          <Trs label="posição (cm)" vals={[trs.pos.x * 100, trs.pos.y * 100, trs.pos.z * 100]} step={0.1} onChange={(k, v) => setTrs('pos', k, v)} />
          <Trs label="rotação (°)" vals={trs.rot as [number, number, number]} step={1} onChange={(k, v) => setTrs('rot', k, v)} />
          <Trs label="escala" vals={[trs.sc.x, trs.sc.y, trs.sc.z]} step={0.01} onChange={(k, v) => setTrs('sc', k, v)} />
          <div className="flex flex-wrap gap-1 mt-2">
            <button type="button" className={btnSmall} onClick={() => replace((y) => ({ ...y, visible: !y.visible }), 'ocultar/mostrar')} title="tecla H">{primary.visible ? 'ocultar' : 'mostrar'}</button>
            <button type="button" className={btnSmall} onClick={excluir} title="Delete">excluir</button>
            <button type="button" className={btnSmall} onClick={duplicar}>duplicar</button>
            <button type="button" className={btnSmall} onClick={fundir} disabled={selected.length < 2}>fundir</button>
            <button type="button" className={btnSmall} onClick={() => replace(flipNormals, 'inverter normais')}>inverter normais</button>
            <button type="button" className={btnSmall} onClick={() => replace(bakeMatrix, 'fixar transformação')} title="aplica a matriz nos vértices">fixar transf.</button>
            {(['x', 'y', 'z'] as const).map((e) => (
              <button key={e} type="button" className={btnSmall} onClick={() => replace((y) => mirror(y, e, 'propria'), `espelhar ${e.toUpperCase()}`)}>espelhar {e.toUpperCase()}</button>
            ))}
          </div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-3 text-[11px] text-gray-600">
            <dt>vértices</dt><dd className="text-right tabular-nums">{primaryStats.vertices.toLocaleString('pt-BR')}</dd>
            <dt>triângulos</dt><dd className="text-right tabular-nums">{primaryStats.triangulos.toLocaleString('pt-BR')}</dd>
            <dt className={primaryStats.arestasBorda ? 'text-amber-700' : ''}>arestas de borda</dt><dd className={`text-right tabular-nums ${primaryStats.arestasBorda ? 'text-amber-700' : ''}`}>{primaryStats.arestasBorda}</dd>
            <dt className={primaryStats.arestasNaoManifold ? 'text-amber-700' : ''}>arestas não-manifold</dt><dd className="text-right tabular-nums">{primaryStats.arestasNaoManifold}</dd>
            <dt className={primaryStats.triangulosDegenerados ? 'text-amber-700' : ''}>triângulos degenerados</dt><dd className="text-right tabular-nums">{primaryStats.triangulosDegenerados}</dd>
            <dt>bbox (cm)</dt><dd className="text-right tabular-nums">{fmtBox(primaryStats.bbox)}</dd>
          </dl>
        </Section>
      )}

      {/* ── modelo inteiro ── */}
      <Section title="Modelo inteiro">
        <div className="flex flex-wrap gap-1">
          <button type="button" className={btnSmall} onClick={() => p.onUpdate(recenter(parts, 'centro'), 'recentrar (centro)')}>centrar na origem</button>
          <button type="button" className={btnSmall} onClick={() => p.onUpdate(recenter(parts, 'base'), 'recentrar (base)')}>apoiar em y=0</button>
          {(['x', 'y', 'z'] as const).map((e) => (
            <button key={e} type="button" className={btnSmall} onClick={() => girarGlobal(e, 90)}>girar 90° {e.toUpperCase()}</button>
          ))}
          <button type="button" className={btnSmall} onClick={removerBocais} disabled={!parts.some((x) => x.marker)}>remover bocais</button>
          <button type="button" className={btnSmall} onClick={resegmentar} title="aplica transformações, deduplica e divide em componentes de novo">re-segmentar</button>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <span className="text-[11px] text-gray-500">escala global</span>
          {[0.01, 0.1, 10, 100].map((f) => (
            <button key={f} type="button" className={btnSmall} onClick={() => escalaGlobal(f)}>×{f}</button>
          ))}
          <EscalaCustom onApply={escalaGlobal} />
        </div>
        <p className="text-[11px] text-gray-400 mt-2">
          Unidade do storage é metro, Y para cima (Three.js). O AltoQi trabalha em centímetros, Z para cima:
          um modelo que chegou deitado precisa de <em>girar 90° X</em>; um que chegou 100× maior, de <em>×0,01</em>.
        </p>
      </Section>

      {/* ── adicionar ── */}
      <Section title="Adicionar parte">
        <div className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-1 items-end">
          <select value={prim.tipo} onChange={(e) => setPrim({ ...prim, tipo: e.target.value as typeof prim.tipo })} className={inputCls}>
            <option value="cilindro">cilindro</option>
            <option value="tubo">tubo</option>
            <option value="caixa">caixa</option>
          </select>
          <Num label={prim.tipo === 'caixa' ? 'larg. cm' : 'Ø ext cm'} value={prim.a} onChange={(v) => setPrim({ ...prim, a: v })} />
          <Num label={prim.tipo === 'caixa' ? 'alt. cm' : prim.tipo === 'tubo' ? 'Ø int cm' : '—'} value={prim.b} onChange={(v) => setPrim({ ...prim, b: v })} disabled={prim.tipo === 'cilindro'} />
          <Num label={prim.tipo === 'caixa' ? 'prof. cm' : 'compr. cm'} value={prim.c} onChange={(v) => setPrim({ ...prim, c: v })} />
          <input type="color" value={prim.cor} onChange={(e) => setPrim({ ...prim, cor: e.target.value })} className="w-9 h-8 p-0 border border-gray-300 rounded cursor-pointer" />
        </div>
        <button type="button" className={`${btnSmall} mt-2`} onClick={adicionarPrimitiva}>+ adicionar primitiva</button>
        <div className="flex items-center gap-2 mt-3">
          <input ref={fileRef} type="file" accept=".stl,.obj,.json" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void importarArquivo(f); e.target.value = '' }} />
          <button type="button" className={btnSmall} onClick={() => fileRef.current?.click()}>importar STL / OBJ / JSON…</button>
          <span className="text-[11px] text-gray-500">unidade do arquivo</span>
          <select value={unidade} onChange={(e) => setUnidade(e.target.value as typeof unidade)} className={inputCls + ' !w-auto'}>
            <option value="mm">mm</option><option value="cm">cm</option><option value="m">m</option>
          </select>
        </div>
        <p className="text-[11px] text-gray-400 mt-1">Malhas locais, na unidade escolhida. Peça STEP/IFC entra como produto pela página inicial (menu &quot;Importar peça STEP / IFC&quot;).</p>
      </Section>

      {/* ── salvar ── */}
      <Section title="Geometria no storage">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={p.geoState.save} disabled={!p.geoState.dirty || p.geoState.saving} className={btnPrimary} title="Ctrl+S">
            {p.geoState.saving ? 'Gravando…' : 'Salvar geometria'}
          </button>
          <button type="button" onClick={p.geoState.reload} disabled={!p.geoState.dirty || p.geoState.saving} className={btnSmall}>descartar</button>
          <button type="button" onClick={p.geoState.restore} disabled={p.geoState.saving || !p.geoState.geoEditadoEm} className={btnSmall} title="volta ao JSON como veio do .aq">restaurar original</button>
          <button type="button" onClick={p.geoState.download} className={btnSmall}>baixar JSON</button>
        </div>
        {p.geoState.dirty && !p.geoState.saving && <p className="text-[11px] text-amber-700 mt-1">alterações não salvas{p.history.lastLabel ? ` — última: ${p.history.lastLabel}` : ''}</p>}
        {p.geoState.msg && <p className={`text-[11px] mt-1 ${p.geoState.msg.tipo === 'erro' ? 'text-red-700' : p.geoState.msg.tipo === 'ok' ? 'text-green-700' : 'text-gray-600'}`}>{p.geoState.msg.texto}</p>}
        {p.geoState.geoEditadoEm && <p className="text-[11px] text-gray-400 mt-1">geometria editada em {new Date(p.geoState.geoEditadoEm).toLocaleString('pt-BR')} · original preservado no storage</p>}
        <p className="text-[11px] text-gray-400 mt-1">Partes ocultas não entram no arquivo salvo. Salvar aplica as matrizes, deduplica (float32, como o import) e grava o <code>{'{pos, col, idx}'}</code> que o viewer público lê.</p>
      </Section>

      {/* ── IFC / .aq ── */}
      <Section title="Exportar IFC4 / .aq">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => p.geoState.exportIfc({ incluirBocais: ifcBocais })} disabled={p.geoState.saving || !parts.some((x) => x.visible)} className={btnPrimary}>
            Exportar IFC
          </button>
          <button type="button" onClick={() => p.geoState.saveAndExportIfc({ incluirBocais: ifcBocais })} disabled={p.geoState.saving || !parts.some((x) => x.visible)} className={btnSmall}>
            {p.geoState.dirty ? 'salvar geometria e exportar IFC' : 'exportar IFC (já salvo)'}
          </button>
          <button type="button" onClick={() => p.geoState.exportAq({ incluirBocais: ifcBocais })} disabled={p.geoState.saving || !parts.some((x) => x.visible)} className={btnSmall} title="biblioteca AltoQi com esta peça (OQ3D + schema 607)">
            Exportar .aq
          </button>
          <Check label="incluir bocais" checked={ifcBocais} onChange={setIfcBocais} />
        </div>
        <p className="text-[11px] text-gray-400 mt-1">
          Exporta <strong>o que está na tela agora</strong>, salvo ou não, separado do storage: um <code>IFCELEMENTASSEMBLY</code> com
          uma <code>IFCBUILDINGELEMENTPROXY</code> por parte visível, malha <code>IFCTRIANGULATEDFACESET</code> em metros, Z para cima,
          cor por face em <code>IFCINDEXEDCOLOURMAP</code>, e as informações do produto em <code>IFCPROPERTYSET</code>. Transformação
          rígida vira <code>IFCLOCALPLACEMENT</code>; escala é aplicada nos vértices. Bocais ficam de fora por padrão — são marcadores do AltoQi.
          <br />O <code>.aq</code> é gerado no servidor pelo <code>www/apps/ingestao/pipeline/geo_to_aq.py</code>: uma biblioteca AltoQi com esta peça, uma malha OQ3D por parte
          (centímetros, Z para cima), as specs como propriedades personalizadas e o insumo com o código. Lido de volta pelo <code>read_aq.py</code> do projeto.
        </p>
      </Section>
    </div>
  )
}

// ─── átomos ──────────────────────────────────────────────────────────────────

function Section({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="border border-gray-200 rounded-lg p-3">
      <header className="flex items-center justify-between mb-2">
        <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">{title}</h3>
        {right}
      </header>
      {children}
    </section>
  )
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-1 cursor-pointer select-none">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

function Trs({ label, vals, step, onChange }: { label: string; vals: [number, number, number]; step: number; onChange: (k: 0 | 1 | 2, v: number) => void }) {
  return (
    <div className="grid grid-cols-[80px_1fr_1fr_1fr] gap-1 items-center mb-1">
      <span className="text-[11px] text-gray-500">{label}</span>
      {([0, 1, 2] as const).map((k) => (
        <input key={k} type="number" step={step} value={Number(vals[k].toFixed(3))}
          onChange={(e) => onChange(k, Number(e.target.value))}
          className={inputCls + ' text-right tabular-nums'} />
      ))}
    </div>
  )
}

function Num({ label, value, onChange, disabled }: { label: string; value: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <Field label={label}>
      <input type="number" step={0.1} min={0} value={value} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} className={inputCls + ' text-right'} />
    </Field>
  )
}

function EscalaCustom({ onApply }: { onApply: (f: number) => void }) {
  const [v, setV] = useState('1')
  return (
    <span className="flex items-center gap-1">
      <input value={v} onChange={(e) => setV(e.target.value)} className={inputCls + ' !w-16 text-right'} inputMode="decimal" />
      <button type="button" className={btnSmall} onClick={() => onApply(Number(v.replace(',', '.')))}>aplicar</button>
    </span>
  )
}

function fmtBox(b: THREE.Box3): string {
  if (b.isEmpty()) return '—'
  const s = b.getSize(new THREE.Vector3())
  return `${cm(s.x)} × ${cm(s.y)} × ${cm(s.z)}`
}
