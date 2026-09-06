'use client'

/**
 * /cad — converter uma peça CAD (.stp/.step/.igs/.ifc) sem criar produto: o serviço de ingestão
 * tessela (`POST /cad/tesselar`, OpenCASCADE / parse_ifc.py), a página mostra o resultado no
 * viewer 3D com unidade, bbox, sólidos e triângulos, e oferece o download em JSON `{pos,col,idx}`,
 * IFC4 (gerado no browser, `ifc-export.ts`) ou `.aq` (`POST /exportar/aq`). É a função que saiu
 * do editor em 2026-09-05 ("adicionar parte de STEP/IFC"), agora como item do menu da página
 * inicial. Para a peça virar um produto num catálogo, use "Importar peça STEP / IFC".
 */

import { FormEvent, useEffect, useState } from 'react'
import { CONVERSORES_URL, gerarAq, tesselar } from '@/servicos/conversores'
import { BimViewer } from '@/components/bim-catalog/BimViewer'
import type { GeoData } from '@/components/bim-catalog/bim-viewer-engine'
import { segment } from '@/components/bim-editor/mesh-model'
import { exportIfc } from '@/components/bim-editor/ifc-export'

interface Tesselado extends GeoData {
  idx: number[]
  partes: Array<{ nome: string; cor?: number[]; tipo?: string; triangulos?: number }>
  unidade: string
  bbox_mm: number[]
  fonte: string
  formato?: 'step' | 'ifc'
  deflexao_mm?: number
  escala_aplicada?: number
  caminho?: string
  segundos: number
  aviso?: string
}

const EXT_CAD = /\.(stp|step|igs|iges|ifc)$/i
const inputCls = 'w-full border border-gray-300 rounded px-2 py-1.5 text-[13px] bg-white'
const btn = 'px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700 disabled:opacity-50'
const btnPrimary = 'px-4 py-2 rounded bg-[#1e40af] text-white text-[13px] font-semibold disabled:opacity-50'

function baixar(blob: Blob, nome: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = nome
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export default function CadPage() {
  const [file, setFile] = useState<File | null>(null)
  const [deflexao, setDeflexao] = useState('0.2')
  const [convertendo, setConvertendo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [geo, setGeo] = useState<Tesselado | null>(null)
  const [geoUrl, setGeoUrl] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const ehIfc = !!file && /\.ifc$/i.test(file.name)
  const nomeBase = geo ? geo.fonte.replace(EXT_CAD, '') : ''

  // o BimViewer lê a geometria por URL: um blob local serve
  useEffect(() => {
    if (!geo) { setGeoUrl(null); return }
    const url = URL.createObjectURL(new Blob([JSON.stringify({ pos: geo.pos, col: geo.col, idx: geo.idx })], { type: 'application/json' }))
    setGeoUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [geo])

  async function converter(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    if (!EXT_CAD.test(file.name)) { setErro('envie .stp, .step, .igs ou .ifc'); return }
    setConvertendo(true); setErro(null); setGeo(null); setMsg(null)
    try {
      const r = await tesselar(file, deflexao)
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data?.message ? (Array.isArray(data.message) ? data.message.join('; ') : String(data.message)) : `serviço respondeu ${r.status}`)
      setGeo(data as Tesselado)
    } catch (e: any) {
      setErro(e?.message?.includes('fetch') ? `falha de rede — o serviço de conversores está de pé em ${CONVERSORES_URL}?` : (e?.message ?? String(e)))
    } finally {
      setConvertendo(false)
    }
  }

  function baixarJson() {
    if (!geo) return
    baixar(new Blob([JSON.stringify({ pos: geo.pos, col: geo.col, idx: geo.idx })], { type: 'application/json' }), `${nomeBase}.json`)
  }

  function baixarIfc() {
    if (!geo) return
    try {
      const parts = segment({ pos: geo.pos, col: geo.col, idx: geo.idx })
      const r = exportIfc(parts, { nome: nomeBase, id: nomeBase, fabricante: geo.formato?.toUpperCase() ?? 'CAD', specs: { Fonte: geo.fonte, 'Unidade do arquivo': geo.unidade } }, { fileName: `${nomeBase}.ifc` })
      baixar(new Blob([r.ifc], { type: 'application/x-step' }), `${nomeBase}.ifc`)
      setMsg(`IFC gerado: ${r.partes} parte(s), ${r.triangulos.toLocaleString('pt-BR')} triângulos, ${(r.bytes / 1024).toFixed(0)} KB.`)
    } catch (e: any) {
      setErro(`IFC: ${e?.message ?? e}`)
    }
  }

  async function baixarAq() {
    if (!geo) return
    setOcupado(true); setErro(null)
    try {
      const r = await gerarAq({
          info: { fabricante: geo.formato?.toUpperCase() ?? 'CAD', linha: 'Peças CAD', nome: nomeBase, descricao: geo.fonte, codigo: nomeBase,
                  specs: { Fonte: geo.fonte, 'Unidade do arquivo': geo.unidade, Triângulos: String(geo.idx.length / 3) }, origem: 'bilds-bim-3d /cad' },
          pos: geo.pos, col: geo.col, idx: geo.idx,
        })
      if (!r.ok) { const b = await r.json().catch(() => ({})); throw new Error(b?.message ? String(b.message) : `serviço respondeu ${r.status}`) }
      const resumoRaw = r.headers.get('X-Aq-Resumo')
      const resumo = resumoRaw ? JSON.parse(decodeURIComponent(resumoRaw)) : null
      baixar(await r.blob(), `${nomeBase}.aq`)
      setMsg(resumo ? `.aq gerado: ${resumo.malhas} malha(s), ${Number(resumo.triangulos).toLocaleString('pt-BR')} triângulos, ${(resumo.bytes / 1024).toFixed(0)} KB.` : '.aq gerado.')
    } catch (e: any) {
      setErro(`.aq: ${e?.message ?? e}`)
    } finally {
      setOcupado(false)
    }
  }

  const bb = geo?.bbox_mm ?? []
  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-[880px] mx-auto">
        <p className="text-[12px] text-gray-500 mb-1"><a href="/" className="hover:underline">← início</a></p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Converter peça CAD</h1>
        <p className="text-[13px] text-gray-600 mb-6">
          Um <code>.stp</code>/<code>.step</code> (B-rep, tesselado com OpenCASCADE) ou <code>.ifc</code> (parse_ifc.py; ifcopenshell
          para arquivo grande) vira a geometria do viewer em metros, Y para cima — para conferir e baixar como JSON, IFC4 ou <code>.aq</code>,
          sem criar produto. Para entrar num catálogo, use <a href="/importar?tipo=cad" className="text-[#1e40af] underline">Importar peça STEP / IFC</a>.
        </p>

        <form onSubmit={converter} className="bg-white border border-gray-200 rounded-lg p-5 flex flex-col gap-4 text-[13px]">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-gray-600 font-medium">Arquivo .stp / .step / .igs / .ifc</span>
            <input type="file" accept=".stp,.step,.igs,.iges,.ifc,.STP,.STEP,.IGS,.IGES,.IFC" required disabled={convertendo} onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[13px]" />
          </label>
          <div className="grid grid-cols-2 gap-3 items-end">
            <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Deflexão da malha (mm, só STEP)</span>
              <select value={deflexao} onChange={(e) => setDeflexao(e.target.value)} className={inputCls} disabled={ehIfc}>
                <option value="0.5">0,5 — leve</option><option value="0.2">0,2 — padrão</option><option value="0.1">0,1 — fina</option><option value="0.05">0,05 — muito fina</option>
              </select>
            </label>
            <div className="flex items-center gap-3">
              <button type="submit" disabled={!file || convertendo} className={btnPrimary}>{convertendo ? 'Convertendo…' : 'Converter'}</button>
              {file && <span className="text-[12px] text-gray-500">{file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB</span>}
            </div>
          </div>
          {erro && <p className="text-[12px] text-red-700">{erro}</p>}
          {convertendo && file && file.size > 20 * 1024 * 1024 && <p className="text-[12px] text-amber-700">arquivo grande: a conversão pode levar minutos (a requisição espera)</p>}
        </form>

        {geo && (
          <section className="mt-5 bg-white border border-gray-200 rounded-lg p-5 text-[13px]">
            <div className="h-[360px] bg-gray-100 rounded-lg overflow-hidden mb-4">
              {geoUrl && <BimViewer key={geoUrl} geoUrl={geoUrl} mode="modal" />}
            </div>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 mb-4">
              {[
                ['Fonte', geo.fonte], ['Formato', geo.formato?.toUpperCase() ?? '—'], ['Unidade do arquivo', geo.unidade],
                ['Dimensões (mm)', bb.length === 3 ? bb.map((v) => v.toFixed(1)).join(' × ') : '—'],
                [geo.formato === 'ifc' ? 'Produtos' : 'Sólidos', String(geo.partes.length)], ['Triângulos', (geo.idx.length / 3).toLocaleString('pt-BR')],
                ['Vértices', (geo.pos.length / 3).toLocaleString('pt-BR')],
                [geo.formato === 'ifc' ? 'Conversor' : 'Deflexão (mm)', geo.formato === 'ifc' ? (geo.caminho ?? 'parse_ifc') : String(geo.deflexao_mm ?? deflexao)],
              ].map(([k, v]) => (
                <div key={k}><dt className="text-[11px] text-gray-400 uppercase tracking-wide">{k}</dt><dd className="font-medium">{v}</dd></div>
              ))}
            </dl>
            {geo.aviso && <p className="text-[12px] text-amber-700 mb-3">{geo.aviso}</p>}
            {geo.partes.length > 1 && (
              <details className="mb-4 text-[12px] text-gray-600"><summary className="cursor-pointer">{geo.partes.length} partes</summary>
                <ul className="mt-1 columns-2">{geo.partes.map((p, i) => <li key={i}>{p.nome}{p.triangulos ? ` · ${p.triangulos} tri` : ''}</li>)}</ul>
              </details>
            )}
            <div className="flex gap-2 flex-wrap items-center">
              <button type="button" onClick={baixarJson} className={btn}>baixar JSON {'{pos,col,idx}'}</button>
              <button type="button" onClick={baixarIfc} className={btn}>baixar IFC4</button>
              <button type="button" onClick={() => void baixarAq()} disabled={ocupado} className={btn}>{ocupado ? 'gerando .aq…' : 'baixar .aq (AltoQi)'}</button>
              <a href="/importar?tipo=cad" className={btnPrimary}>Importar como produto →</a>
            </div>
            {msg && <p className="text-[12px] text-green-700 mt-3">{msg}</p>}
          </section>
        )}
      </div>
    </main>
  )
}
