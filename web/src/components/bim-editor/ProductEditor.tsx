'use client'

/**
 * ProductEditor — a tela de edição de um produto: viewport 3D à esquerda,
 * painéis (geometria / informações / catálogo) à direita.
 *
 * Estado de geometria: histórico de snapshots `{ parts, label }` (undo/redo).
 * As partes são imutáveis; cada operação substitui só as que mudaram, então um
 * snapshot custa o array de referências, não os buffers. `dirty` é comparação de
 * referência entre `present.parts` e o último estado salvo/carregado.
 *
 * Salvar = bake(parts) → PUT /geometrias/:id → invalida o cache do viewer.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { CATALOGO_URL } from '@/servicos/catalogo'
import { EDITOR_URL, editorJson } from '@/servicos/editor'
import { gerarAq } from '@/servicos/conversores'
import type { GeoData } from '../bim-catalog/bim-viewer-engine'
import { invalidateGeo } from '../bim-catalog/bim-viewer-engine'
import type { PocCatalog, PocProduct } from '../bim-catalog/types'
import { EditorViewport, type Tool, type ViewPreset } from './EditorViewport'
import { GeometryPanel, type EditorUi } from './GeometryPanel'
import { InfoForm, type ProdutoDto } from './InfoForm'
import { bake, bakeMatrix, segment, type Part } from './mesh-model'
import { exportIfc as buildIfc } from './ifc-export'
import { BotaoApagar } from '../BotaoApagar'

interface Snapshot { parts: Part[]; label: string }
interface History { past: Snapshot[]; present: Snapshot; future: Snapshot[] }
const HISTORY_MAX = 60

interface Props {
  empresa: string
  catalogSlug: string
  catalog: PocCatalog
  products: PocProduct[]
  produto: ProdutoDto
}

type Tab = 'geometria' | 'informacoes'

export function ProductEditor(props: Props) {
  const router = useRouter()
  const [produto, setProduto] = useState<ProdutoDto>(props.produto)
  const [catalog, setCatalog] = useState<PocCatalog>(props.catalog)
  const [tab, setTab] = useState<Tab>('geometria')

  // ── geometria ────────────────────────────────────────────────────────────
  const [hist, setHist] = useState<History | null>(null)
  const savedRef = useRef<Part[] | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro' | 'info'; texto: string } | null>(null)
  const [ghost, setGhost] = useState<GeoData | null>(null)
  const [fitRequest, setFitRequest] = useState(0)
  const [viewRequest, setViewRequest] = useState<{ n: number; view: ViewPreset }>({ n: 0, view: 'iso' })
  const [ui, setUiState] = useState<EditorUi>({
    tool: 'select', wireframe: false, snap: false, showGrid: true, showMarkers: true,
    clipEnabled: false, clipFrac: 0.5, ghostOn: false,
  })
  const setUi = useCallback((patch: Partial<EditorUi>) => setUiState((u) => ({ ...u, ...patch })), [])

  const geoUrl = `${CATALOGO_URL}/geometrias/${produto._id}`
  const geoUrlEditor = `${EDITOR_URL}/geometrias/${produto._id}`

  const loadGeo = useCallback(async () => {
    setLoading(true)
    setMsg(null)
    try {
      const res = await fetch(`${geoUrl}?t=${Date.now()}`, { cache: 'no-store' })
      if (!res.ok) throw new Error(`geometria: HTTP ${res.status}`)
      const data = (await res.json()) as GeoData
      const parts = segment(data)
      savedRef.current = parts
      setHist({ past: [], present: { parts, label: 'carregado' }, future: [] })
      setSelected([])
      setFitRequest((n) => n + 1)
      setMsg({ tipo: 'info', texto: `${parts.length} parte(s) · ${(data.idx?.length ?? 0) / 3} triângulos` })
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: e.message ?? String(e) })
    } finally {
      setLoading(false)
    }
  }, [geoUrl])

  useEffect(() => { void loadGeo() }, [loadGeo])

  // fantasma do original — carrega uma vez quando ligado
  useEffect(() => {
    if (!ui.ghostOn || ghost) return
    fetch(`${geoUrlEditor}/original?t=${Date.now()}`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`original: HTTP ${r.status}`))))
      .then((d: GeoData) => setGhost(d))
      .catch((e) => setMsg({ tipo: 'erro', texto: e.message }))
  }, [ui.ghostOn, ghost, geoUrl])

  const parts = hist?.present.parts ?? []
  const dirty = !!hist && hist.present.parts !== savedRef.current

  const update = useCallback((next: Part[], label: string) => {
    setHist((h) => {
      if (!h) return h
      const past = [...h.past, h.present]
      if (past.length > HISTORY_MAX) past.shift()
      return { past, present: { parts: next, label }, future: [] }
    })
  }, [])

  const undo = useCallback(() => setHist((h) => {
    if (!h || !h.past.length) return h
    const prev = h.past[h.past.length - 1]
    return { past: h.past.slice(0, -1), present: prev, future: [h.present, ...h.future] }
  }), [])
  const redo = useCallback(() => setHist((h) => {
    if (!h || !h.future.length) return h
    const [next, ...rest] = h.future
    return { past: [...h.past, h.present], present: next, future: rest }
  }), [])

  // seleção: só ids que ainda existem
  useEffect(() => {
    const ids = new Set(parts.map((p) => p.id))
    setSelected((s) => (s.every((id) => ids.has(id)) ? s : s.filter((id) => ids.has(id))))
  }, [parts])

  const onSelect = useCallback((ids: string[], additive: boolean) => {
    setSelected((cur) => {
      if (!additive) return ids
      const set = new Set(cur)
      for (const id of ids) { if (set.has(id)) set.delete(id); else set.add(id) }
      return [...set]
    })
  }, [])

  const onCommitMatrix = useCallback((changes: Array<{ id: string; matrix: number[] }>) => {
    const map = new Map(changes.map((c) => [c.id, c.matrix]))
    setHist((h) => {
      if (!h) return h
      const next = h.present.parts.map((p) => (map.has(p.id) ? { ...p, matrix: map.get(p.id)! } : p))
      const past = [...h.past, h.present]
      if (past.length > HISTORY_MAX) past.shift()
      return { past, present: { parts: next, label: ui.tool === 'translate' ? 'mover' : ui.tool === 'rotate' ? 'girar' : 'escalar' }, future: [] }
    })
  }, [ui.tool])

  /** Gera o IFC4 do estado atual (independente do storage) e dispara o download. */
  function exportIfc(opts: { incluirBocais: boolean }, partsOverride?: Part[]) {
    const src = partsOverride ?? hist?.present.parts
    if (!src) return
    try {
      const r = buildIfc(src, {
        nome: produto.nome,
        id: produto.id,
        serie: produto.serie,
        fabricante: catalog.manufacturer,
        catalogo: catalog.title,
        specs: produto.specs,
        potencia: produto.potencia,
        conexoes: produto.conexoes,
        produtoId: produto._id,
      }, { incluirBocais: opts.incluirBocais, fileName: `${produto.id}.ifc` })
      const blob = new Blob([r.ifc], { type: 'application/x-step' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${produto.id}.ifc`
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 2000)
      setMsg({ tipo: 'ok', texto: `IFC gerado: ${r.partes} parte(s), ${r.triangulos.toLocaleString('pt-BR')} triângulos, ${(r.bytes / 1024).toFixed(0)} KB.` })
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: `IFC: ${e.message ?? String(e)}` })
    }
  }

  /** Partes visíveis com a matriz aplicada, no formato que o geo_to_aq.py espera. */
  function partesParaExportar(src: Part[], incluirBocais: boolean) {
    return src
      .filter((p) => p.visible && (incluirBocais || !p.marker))
      .map(bakeMatrix)
      .map((p) => ({ nome: p.nome, pos: Array.from(p.pos), col: p.col ? Array.from(p.col) : null, idx: Array.from(p.idx) }))
  }

  /** Gera o .aq no servidor (OQ3D + schema 607 do eng-reversa) e baixa. */
  async function exportAq(opts: { incluirBocais: boolean }) {
    if (!hist) return
    const partes = partesParaExportar(hist.present.parts, opts.incluirBocais)
    if (!partes.length) { setMsg({ tipo: 'erro', texto: 'nada visível para exportar' }); return }
    setSaving(true)
    setMsg(null)
    try {
      const r = await gerarAq({
          info: {
            fabricante: catalog.manufacturer,
            linha: catalog.title,
            nome: produto.nome,
            descricao: produto.nome,
            codigo: produto.id,
            specs: produto.specs,
            origem: `bilds-bim-3d poc-edicao · produto ${produto._id}`,
          },
          partes,
        })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body?.message ? String(body.message) : `API ${r.status}`)
      }
      const blob = await r.blob()
      const resumoRaw = r.headers.get('X-Aq-Resumo')
      const resumo = resumoRaw ? JSON.parse(decodeURIComponent(resumoRaw)) : null
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${produto.id}.aq`
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 2000)
      setMsg({ tipo: 'ok', texto: resumo ? `.aq gerado: ${resumo.malhas} malha(s), ${Number(resumo.triangulos).toLocaleString('pt-BR')} triângulos, ${(resumo.bytes / 1024).toFixed(0)} KB.` : '.aq gerado.' })
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: `.aq: ${e.message ?? String(e)}` })
    } finally {
      setSaving(false)
    }
  }

  async function saveAndExportIfc(opts: { incluirBocais: boolean }) {
    if (!hist) return
    if (dirty) {
      const ok = await save()
      if (!ok) return
    }
    exportIfc(opts, hist.present.parts)
  }

  async function save(): Promise<boolean> {
    if (!hist) return false
    setSaving(true)
    setMsg(null)
    try {
      const geo = bake(hist.present.parts)
      if (!geo.idx.length) throw new Error('nada visível para salvar — mostre ao menos uma parte')
      const r = await editorJson<{ vertices: number; triangulos: number; bytes: number; geoEditadoEm: string; backupFeito: boolean; miniatura?: string }>(
        `/geometrias/${produto._id}`, { method: 'PUT', body: JSON.stringify(geo) },
      )
      savedRef.current = hist.present.parts
      invalidateGeo(geoUrl)
      setProduto((p) => ({ ...p, geoEditadoEm: r.geoEditadoEm }))
      setHist((h) => h) // força re-render do dirty
      setMsg({ tipo: 'ok', texto: `Gravado: ${r.vertices.toLocaleString('pt-BR')} vértices, ${r.triangulos.toLocaleString('pt-BR')} triângulos, ${(r.bytes / 1024).toFixed(0)} KB${r.backupFeito ? ' — original preservado' : ''}${r.miniatura ? ' — miniatura em regeneração' : ''}.` })
      return true
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: e.message ?? String(e) })
      return false
    } finally {
      setSaving(false)
    }
  }

  async function restore() {
    if (!confirm('Voltar a geometria ao original do .aq? A versão editada no storage será substituída.')) return
    setSaving(true)
    try {
      await editorJson(`/geometrias/${produto._id}/restaurar`, { method: 'POST' })
      invalidateGeo(geoUrl)
      setProduto((p) => ({ ...p, geoEditadoEm: null }))
      setGhost(null)
      await loadGeo()
      setMsg({ tipo: 'ok', texto: 'Geometria original restaurada.' })
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: e.message ?? String(e) })
    } finally {
      setSaving(false)
    }
  }

  function download() {
    if (!hist) return
    const blob = new Blob([JSON.stringify(bake(hist.present.parts))], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${produto.id}.json`
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }

  function reload() {
    if (dirty && !confirm('Descartar as alterações não salvas da geometria?')) return
    void loadGeo()
  }

  // ── atalhos ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return
      const mod = e.ctrlKey || e.metaKey
      if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return }
      if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); return }
      if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); if (dirty && !saving) void save(); return }
      if (mod) return
      const tools: Record<string, Tool> = { '1': 'select', '2': 'translate', '3': 'rotate', '4': 'scale' }
      if (tools[e.key]) { setUi({ tool: tools[e.key] }); return }
      if (e.key === 'f' || e.key === 'F') { setFitRequest((n) => n + 1); return }
      if (e.key === 'Escape') { setSelected([]); return }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected.length) {
        const set = new Set(selected)
        update(parts.filter((p) => !set.has(p.id)), `excluir ${selected.length} parte(s)`)
        setSelected([])
        return
      }
      if ((e.key === 'h' || e.key === 'H') && selected.length) {
        const set = new Set(selected)
        update(parts.map((p) => (set.has(p.id) ? { ...p, visible: !p.visible } : p)), 'ocultar/mostrar')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, parts, dirty, saving, undo, redo, update, setUi]) // eslint-disable-line react-hooks/exhaustive-deps

  // aviso ao sair com alterações
  useEffect(() => {
    if (!dirty) return
    const h = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [dirty])

  const series = useMemo(() => Array.from(new Set(props.products.map((p) => p.serie).filter(Boolean))), [props.products])
  const publicUrl = `/${props.empresa}/${props.catalogSlug}`

  return (
    <div className="h-screen flex flex-col bg-white text-gray-900" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* barra superior */}
      <header className="flex items-center gap-3 px-4 h-12 border-b border-gray-200 bg-[#002D72] text-white shrink-0">
        <a href={`${publicUrl}/editar`} className="text-[12px] text-blue-200 hover:text-white">{catalog.manufacturer} · {catalog.title}</a>
        <span className="text-blue-300">/</span>
        <select
          value={produto._id}
          onChange={(e) => {
            if (dirty && !confirm('Há alterações de geometria não salvas. Trocar de produto e descartá-las?')) return
            router.push(`${publicUrl}/editar/${e.target.value}`)
          }}
          className="bg-white/10 text-white text-[13px] rounded px-2 py-1 max-w-[380px] border border-white/20"
        >
          {props.products.map((p) => <option key={p._id} value={p._id} className="text-gray-900">{p.nome}</option>)}
        </select>
        <span className="flex-1" />
        {dirty && <span className="text-[11px] px-2 py-0.5 rounded bg-amber-400 text-amber-950 font-semibold">geometria não salva</span>}
        <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="text-[12px] text-blue-200 hover:text-white">ver catálogo ↗</a>
        <BotaoApagar rota={`/produtos/${produto._id}`} rotulo="apagar peça" depois={`${publicUrl}/editar`}
          className="px-2 py-1 rounded border border-red-300/60 text-[12px] text-red-200 hover:bg-red-500/20"
          confirmacao={`Apagar a peça "${produto.nome}"? A geometria e a miniatura só saem se nenhuma outra peça as compartilha. Não tem volta.`} />
      </header>

      <div className="flex flex-1 min-h-0">
        {/* viewport */}
        <div className="flex-1 relative min-w-0">
          <EditorViewport
            parts={parts}
            selected={selected}
            tool={ui.tool}
            wireframe={ui.wireframe}
            snap={ui.snap}
            showGrid={ui.showGrid}
            showMarkers={ui.showMarkers}
            ghost={ui.ghostOn ? ghost : null}
            clip={{ enabled: ui.clipEnabled, frac: ui.clipFrac }}
            fitRequest={fitRequest}
            viewRequest={viewRequest}
            onSelect={onSelect}
            onCommitMatrix={onCommitMatrix}
          />
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/60 text-gray-600 text-sm">carregando geometria…</div>
          )}
          <div className="absolute left-3 bottom-3 text-[11px] text-gray-500 bg-white/80 rounded px-2 py-1 pointer-events-none">
            clique seleciona · shift+clique acrescenta · 1-4 ferramentas · F enquadra · H oculta · Del exclui · Ctrl+Z desfaz · Ctrl+S salva
          </div>
        </div>

        {/* painel */}
        <aside className="w-[420px] shrink-0 border-l border-gray-200 flex flex-col min-h-0">
          <nav className="flex border-b border-gray-200 shrink-0">
            {([['geometria', 'Geometria'], ['informacoes', 'Informações']] as Array<[Tab, string]>).map(([id, label]) => (
              <button key={id} type="button" onClick={() => setTab(id)}
                className={`flex-1 py-2 text-[12px] font-semibold border-b-2 ${tab === id ? 'border-[#1e40af] text-[#1e40af]' : 'border-transparent text-gray-500 hover:text-gray-800'}`}>
                {label}
              </button>
            ))}
          </nav>
          <div className="flex-1 overflow-y-auto p-3">
            {tab === 'geometria' && hist && (
              <GeometryPanel
                parts={parts}
                selected={selected}
                onSelect={onSelect}
                onUpdate={update}
                ui={ui}
                setUi={setUi}
                onFit={() => setFitRequest((n) => n + 1)}
                onView={(view) => setViewRequest((v) => ({ n: v.n + 1, view }))}
                history={{ canUndo: hist.past.length > 0, canRedo: hist.future.length > 0, undo, redo, lastLabel: hist.present.label }}
                geoState={{ dirty, saving, msg, geoEditadoEm: produto.geoEditadoEm, save: () => { void save() }, restore, download, reload, exportIfc, saveAndExportIfc: (o) => { void saveAndExportIfc(o) }, exportAq: (o) => { void exportAq(o) } }}
              />
            )}
            {tab === 'informacoes' && (
              <InfoForm produto={produto} series={series} onSaved={(p) => { setProduto(p); router.refresh() }} />
            )}

          </div>
        </aside>
      </div>
    </div>
  )
}
