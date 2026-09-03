'use client'

/**
 * InfoForm — edição das informações do produto que vivem no Mongo
 * (nome, série, specs, curva Q-H, potência, conexões) e dos metadados do
 * catálogo (título, fabricante, layout). Fala direto com a API da POC:
 * PATCH /produtos/:id e PATCH /catalogos/:id.
 *
 * `infoOriginal` (gravado pela API na primeira edição) permite mostrar o valor
 * que veio do .aq e voltar campo a campo.
 */

import { useEffect, useMemo, useState } from 'react'
import { apiJson } from '@/lib/api'
import type { PocCatalog } from '../bim-catalog/types'

export interface ProdutoDto {
  _id: string
  catalogId: string
  importId: string
  id: string
  nome: string
  serie: string
  specs: Record<string, string>
  curva: number[][] | null
  potencia: number | null
  conexoes: string | null
  geoKey: string
  geoUrl: string
  thumbUrl: string | null
  editadoEm: string | null
  geoEditadoEm: string | null
  infoOriginal: Partial<Record<'nome' | 'serie' | 'specs' | 'curva' | 'potencia' | 'conexoes', unknown>> | null
  createdAt: string
}

interface SpecRow { k: string; v: string }

interface InfoFormProps {
  produto: ProdutoDto
  series: string[]
  onSaved: (p: ProdutoDto) => void
}

export function InfoForm({ produto, series, onSaved }: InfoFormProps) {
  const [nome, setNome] = useState(produto.nome)
  const [serie, setSerie] = useState(produto.serie ?? '')
  const [specs, setSpecs] = useState<SpecRow[]>(() => Object.entries(produto.specs ?? {}).map(([k, v]) => ({ k, v: String(v) })))
  const [curva, setCurva] = useState<number[][]>(() => (produto.curva ?? []).map((p) => [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0, p[3] ?? 0]))
  const [temCurva, setTemCurva] = useState(!!produto.curva && produto.curva.length > 0)
  const [potencia, setPotencia] = useState<string>(produto.potencia == null ? '' : String(produto.potencia))
  const [conexoes, setConexoes] = useState(produto.conexoes ?? '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro'; texto: string } | null>(null)

  // troca de produto → repõe o formulário. (Não depende de `editadoEm`: depois de
  // salvar, o formulário já contém o que foi salvo, e resetar aqui apagava a mensagem.)
  useEffect(() => {
    setNome(produto.nome)
    setSerie(produto.serie ?? '')
    setSpecs(Object.entries(produto.specs ?? {}).map(([k, v]) => ({ k, v: String(v) })))
    setCurva((produto.curva ?? []).map((p) => [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0, p[3] ?? 0]))
    setTemCurva(!!produto.curva && produto.curva.length > 0)
    setPotencia(produto.potencia == null ? '' : String(produto.potencia))
    setConexoes(produto.conexoes ?? '')
    setMsg(null)
  }, [produto._id]) // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = useMemo(() => {
    const specsObj = Object.fromEntries(specs.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v]))
    const curvaAtual = temCurva ? curva : null
    return (
      nome !== produto.nome ||
      serie !== (produto.serie ?? '') ||
      JSON.stringify(specsObj) !== JSON.stringify(produto.specs ?? {}) ||
      JSON.stringify(curvaAtual) !== JSON.stringify(produto.curva && produto.curva.length ? produto.curva.map((p) => [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0, p[3] ?? 0]) : null) ||
      potencia !== (produto.potencia == null ? '' : String(produto.potencia)) ||
      conexoes !== (produto.conexoes ?? '')
    )
  }, [nome, serie, specs, curva, temCurva, potencia, conexoes, produto])

  async function salvar() {
    setSaving(true)
    setMsg(null)
    try {
      const body = {
        nome,
        serie,
        specs: Object.fromEntries(specs.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v])),
        curva: temCurva ? curva.filter((p) => p.every((n) => Number.isFinite(n))) : null,
        potencia: potencia.trim() === '' ? null : Number(potencia),
        conexoes: conexoes.trim() === '' ? null : conexoes,
      }
      if (body.potencia !== null && !Number.isFinite(body.potencia)) throw new Error('Potência deve ser um número')
      const salvo = await apiJson<ProdutoDto>(`/produtos/${produto._id}`, { method: 'PATCH', body: JSON.stringify(body) })
      onSaved(salvo)
      setMsg({ tipo: 'ok', texto: 'Informações salvas.' })
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: e.message ?? String(e) })
    } finally {
      setSaving(false)
    }
  }

  const orig = produto.infoOriginal
  function Original({ campo, onRestore }: { campo: keyof NonNullable<typeof orig>; onRestore: () => void }) {
    if (!orig || !(campo in orig)) return null
    const v = orig[campo]
    const atual = (produto as any)[campo]
    if (JSON.stringify(v) === JSON.stringify(atual)) return null
    const texto = typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : String(v ?? '—')
    return (
      <div className="text-[11px] text-amber-700 mt-1 flex gap-2 items-baseline">
        <span className="truncate" title={texto}>do .aq: {texto}</span>
        <button type="button" onClick={onRestore} className="underline shrink-0">voltar</button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 text-[13px]">
      <Field label="Nome">
        <input value={nome} onChange={(e) => setNome(e.target.value)} className={inputCls} />
        <Original campo="nome" onRestore={() => setNome(String(orig?.nome ?? ''))} />
      </Field>

      <Field label="Série / família">
        <input value={serie} onChange={(e) => setSerie(e.target.value)} className={inputCls} list="series-existentes" />
        <datalist id="series-existentes">{series.map((s) => <option key={s} value={s} />)}</datalist>
        <Original campo="serie" onRestore={() => setSerie(String(orig?.serie ?? ''))} />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Potência (cv)">
          <input value={potencia} onChange={(e) => setPotencia(e.target.value)} className={inputCls} inputMode="decimal" placeholder="—" />
          <Original campo="potencia" onRestore={() => setPotencia(orig?.potencia == null ? '' : String(orig.potencia))} />
        </Field>
        <Field label="Conexões">
          <input value={conexoes} onChange={(e) => setConexoes(e.target.value)} className={inputCls} placeholder="—" />
          <Original campo="conexoes" onRestore={() => setConexoes(String(orig?.conexoes ?? ''))} />
        </Field>
      </div>

      <Field label={`Especificações (${specs.length})`}>
        <div className="flex flex-col gap-1.5">
          {specs.map((row, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-1.5">
              <input value={row.k} onChange={(e) => setSpecs(specs.map((r, j) => (j === i ? { ...r, k: e.target.value } : r)))} className={inputCls} placeholder="chave" />
              <input value={row.v} onChange={(e) => setSpecs(specs.map((r, j) => (j === i ? { ...r, v: e.target.value } : r)))} className={inputCls} placeholder="valor" />
              <button type="button" onClick={() => setSpecs(specs.filter((_, j) => j !== i))} className={btnGhost} title="remover">✕</button>
            </div>
          ))}
          <button type="button" onClick={() => setSpecs([...specs, { k: '', v: '' }])} className={btnSmall}>+ especificação</button>
        </div>
        <Original campo="specs" onRestore={() => setSpecs(Object.entries((orig?.specs as Record<string, string>) ?? {}).map(([k, v]) => ({ k, v: String(v) })))} />
      </Field>

      <Field label="Curva Q-H">
        <label className="flex items-center gap-2 mb-2 text-[12px] text-gray-600">
          <input type="checkbox" checked={temCurva} onChange={(e) => setTemCurva(e.target.checked)} />
          produto tem curva (define o layout <code>series-rows</code> no import)
        </label>
        {temCurva && (
          <div className="flex flex-col gap-1">
            <div className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-1 text-[10px] uppercase tracking-wide text-gray-400 px-1">
              <span>Vazão (m³/h)</span><span>Altura (mca)</span><span>Potência</span><span>Rend. (%)</span><span />
            </div>
            {curva.map((p, i) => (
              <div key={i} className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-1">
                {[0, 1, 2, 3].map((k) => (
                  <input
                    key={k}
                    value={Number.isFinite(p[k]) ? p[k] : ''}
                    onChange={(e) => {
                      const v = e.target.value === '' ? NaN : Number(e.target.value)
                      setCurva(curva.map((q, j) => (j === i ? q.map((x, kk) => (kk === k ? v : x)) : q)))
                    }}
                    className={inputCls + ' text-right'}
                    inputMode="decimal"
                  />
                ))}
                <button type="button" onClick={() => setCurva(curva.filter((_, j) => j !== i))} className={btnGhost}>✕</button>
              </div>
            ))}
            <div className="flex gap-2">
              <button type="button" onClick={() => setCurva([...curva, [curva.length ? curva[curva.length - 1][0] + 1 : 0, 0, 0, 0]])} className={btnSmall}>+ ponto</button>
              <button type="button" onClick={() => setCurva([...curva].sort((a, b) => a[0] - b[0]))} className={btnSmall}>ordenar por vazão</button>
            </div>
          </div>
        )}
        <Original campo="curva" onRestore={() => { const c = (orig?.curva as number[][] | null) ?? null; setTemCurva(!!c && c.length > 0); setCurva((c ?? []).map((p) => [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0, p[3] ?? 0])) }} />
      </Field>

      <div className="flex items-center gap-3 pt-2 border-t border-gray-200">
        <button type="button" onClick={salvar} disabled={!dirty || saving} className={btnPrimary}>
          {saving ? 'Salvando…' : 'Salvar informações'}
        </button>
        {dirty && !saving && <span className="text-[11px] text-amber-700">alterações não salvas</span>}
        {msg && <span className={`text-[11px] ${msg.tipo === 'ok' ? 'text-green-700' : 'text-red-700'}`}>{msg.texto}</span>}
      </div>
      <p className="text-[11px] text-gray-400">
        id no .aq: <code>{produto.id}</code> · import <code>{produto.importId.slice(0, 8)}</code>
        {produto.editadoEm && <> · editado em {new Date(produto.editadoEm).toLocaleString('pt-BR')}</>}
      </p>
    </div>
  )
}

// ─── Catálogo ────────────────────────────────────────────────────────────────

export function CatalogForm({ catalog, onSaved }: { catalog: PocCatalog; onSaved: (c: PocCatalog) => void }) {
  const [title, setTitle] = useState(catalog.title)
  const [manufacturer, setManufacturer] = useState(catalog.manufacturer)
  const [layout, setLayout] = useState(catalog.layout)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const dirty = title !== catalog.title || manufacturer !== catalog.manufacturer || layout !== catalog.layout

  async function salvar() {
    setSaving(true)
    setMsg(null)
    try {
      const c = await apiJson<PocCatalog>(`/catalogos/${catalog.id}`, { method: 'PATCH', body: JSON.stringify({ title, manufacturer, layout }) })
      onSaved(c)
      setMsg('Catálogo salvo.')
    } catch (e: any) {
      setMsg(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 text-[13px]">
      <Field label="Título"><input value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} /></Field>
      <Field label="Fabricante"><input value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} className={inputCls} /></Field>
      <Field label="Layout">
        <select value={layout} onChange={(e) => setLayout(e.target.value)} className={inputCls}>
          <option value="series-rows">series-rows — famílias em linhas (bombas, curva Q-H)</option>
          <option value="catalog-grid">catalog-grid — grade com filtros (conexões)</option>
        </select>
      </Field>
      <div className="flex items-center gap-3">
        <button type="button" onClick={salvar} disabled={!dirty || saving} className={btnPrimary}>{saving ? 'Salvando…' : 'Salvar catálogo'}</button>
        {msg && <span className="text-[11px] text-gray-600">{msg}</span>}
      </div>
    </div>
  )
}

// ─── átomos ──────────────────────────────────────────────────────────────────

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wide text-gray-500">{label}</span>
      {children}
    </label>
  )
}

export const inputCls = 'border border-gray-300 rounded px-2 py-1 text-[13px] bg-white focus:outline-none focus:border-blue-600 w-full'
export const btnPrimary = 'px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold disabled:opacity-40 disabled:cursor-default cursor-pointer'
export const btnSmall = 'px-2 py-1 rounded border border-gray-300 bg-white text-[12px] text-gray-700 hover:border-gray-400 cursor-pointer disabled:opacity-40 disabled:cursor-default'
export const btnGhost = 'px-2 py-1 text-gray-400 hover:text-red-600 cursor-pointer text-[12px]'
