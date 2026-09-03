'use client'

/**
 * /importar-step — sobe um .stp/.step (tesselado com OpenCASCADE) ou um .ifc
 * (parse_ifc.py exato, ou ifcopenshell para arquivo grande); a API cria a
 * importação e responde na hora; esta página acompanha o status até publicar.
 *
 * Por que assíncrono: um Revit de 130 MB leva ~4 min para tesselar. A versão
 * síncrona morria no timeout do servidor e o browser mostrava só "Failed to
 * fetch", sem dizer nada. Agora o progresso do conversor aparece aqui.
 * Sem login (rota fora do matcher do middleware), como o resto da POC de edição.
 */

import { FormEvent, useEffect, useRef, useState } from 'react'
import { API_URL } from '@/lib/api'
import { Field, btnPrimary, inputCls } from '@/components/bim-editor/InfoForm'

interface Status {
  importId: string
  status: 'recebido' | 'parseando' | 'gravando' | 'publicado' | 'falhou' | string
  fileName: string
  note: string | null
  error: string | null
  segundos: number
  produtoId?: string
  nome?: string
  editorUrl?: string
  catalogoUrl?: string
  specs?: Record<string, string>
  thumbUrl?: string | null
}

const GRANDE_MB = 20

const ETAPAS: Array<[string, string]> = [
  ['recebido', 'recebido'],
  ['parseando', 'convertendo'],
  ['gravando', 'gravando'],
  ['publicado', 'publicado'],
]

export default function ImportarStepPage() {
  const [file, setFile] = useState<File | null>(null)
  const [fabricante, setFabricante] = useState('')
  const [catalogo, setCatalogo] = useState('')
  const [nome, setNome] = useState('')
  const [deflexao, setDeflexao] = useState('0.2')
  const [empresa, setEmpresa] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [progressoUpload, setProgressoUpload] = useState<number | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [st, setSt] = useState<Status | null>(null)
  const [tick, setTick] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const emAndamento = !!st && st.status !== 'publicado' && st.status !== 'falhou'

  // polling do status
  useEffect(() => {
    if (!st || !emAndamento) {
      if (timer.current) { clearInterval(timer.current); timer.current = null }
      return
    }
    timer.current = setInterval(async () => {
      try {
        const r = await fetch(`${API_URL}/cad/importacoes/${st.importId}`, { cache: 'no-store' })
        if (r.ok) setSt((await r.json()) as Status)
        setTick((t) => t + 1)
      } catch { /* API fora momentaneamente — tenta de novo */ }
    }, 2000)
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [st?.importId, emAndamento]) // eslint-disable-line react-hooks/exhaustive-deps

  function enviar(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    setEnviando(true)
    setErro(null)
    setSt(null)
    setProgressoUpload(0)
    const fd = new FormData()
    fd.append('file', file)
    if (fabricante.trim()) fd.append('fabricante', fabricante.trim())
    if (catalogo.trim()) fd.append('catalogo', catalogo.trim())
    fd.append('nome', nome || file.name.replace(/\.(stp|step|ifc)$/i, ''))
    fd.append('deflexao', deflexao)
    if (empresa.trim()) fd.append('empresa', empresa.trim())

    // XHR em vez de fetch só para ter progresso de upload — 130 MB demoram
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_URL}/cad/importar`)
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) setProgressoUpload(Math.round((ev.loaded / ev.total) * 100)) }
    xhr.onerror = () => { setErro('falha de rede ao enviar — a API está de pé em ' + API_URL + '?'); setEnviando(false) }
    xhr.onload = () => {
      setEnviando(false)
      setProgressoUpload(null)
      let data: any = {}
      try { data = JSON.parse(xhr.responseText) } catch { /* vazio */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        setErro(data?.message ? String(data.message) : `API ${xhr.status}`)
        return
      }
      setSt({ importId: data.importId, status: data.status ?? 'recebido', fileName: file.name, note: null, error: null, segundos: 0 })
    }
    xhr.send(fd)
  }

  const grande = !!file && file.size > GRANDE_MB * 1024 * 1024
  const ehIfc = !!file && /\.ifc$/i.test(file.name)

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 flex items-start justify-center py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="w-full max-w-[600px]">
        <p className="text-[12px] text-gray-500 mb-1">bilds BIM 3D · POC de edição</p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Importar peça CAD — STEP ou IFC</h1>
        <p className="text-[13px] text-gray-600 mb-6">
          STEP é tesselado no servidor com OpenCASCADE; IFC pequeno passa pelo <code>parse_ifc.py</code> do projeto (cores por face exatas),
          IFC grande pelo <code>ifcopenshell</code> (C++, cores por material). Tudo vira metros, Y-up, e entra num catálogo como produto.
          Depois é só editar, e exportar em IFC4 ou <code>.aq</code>.
        </p>

        <form onSubmit={enviar} className="bg-white border border-gray-200 rounded-lg p-5 flex flex-col gap-4 text-[13px]">
          <Field label="Arquivo .stp / .step / .ifc">
            <input type="file" accept=".stp,.step,.ifc,.STP,.STEP,.IFC" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[13px]" />
          </Field>
          {file && (
            <p className="text-[12px] text-gray-500 -mt-2">
              {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
              {grande && <span className="text-amber-700"> · arquivo grande: {ehIfc ? 'um Revit de 130 MB leva ~4 min e ~3,5 GB de RAM no servidor' : 'a tesselação pode levar minutos'} — a página acompanha o progresso</span>}
            </p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Fabricante (série no catálogo)"><input value={fabricante} onChange={(e) => setFabricante(e.target.value)} className={inputCls} placeholder="STEP ou IFC" /></Field>
            <Field label="Catálogo (título)"><input value={catalogo} onChange={(e) => setCatalogo(e.target.value)} className={inputCls} placeholder="Peças STEP ou Peças IFC" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nome da peça (vazio = nome do arquivo)"><input value={nome} onChange={(e) => setNome(e.target.value)} className={inputCls} placeholder={file ? file.name.replace(/\.(stp|step|ifc)$/i, '') : ''} /></Field>
            <Field label="Deflexão da malha (mm, só STEP)">
              <select value={deflexao} onChange={(e) => setDeflexao(e.target.value)} className={inputCls} disabled={ehIfc}>
                <option value="0.5">0,5 — leve</option>
                <option value="0.2">0,2 — padrão</option>
                <option value="0.1">0,1 — fina</option>
                <option value="0.05">0,05 — muito fina</option>
              </select>
            </Field>
          </div>
          <Field label="Empresa (customUrl; vazio = a primeira cadastrada)"><input value={empresa} onChange={(e) => setEmpresa(e.target.value)} className={inputCls} placeholder="poc-edicao" /></Field>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={!file || enviando || emAndamento} className={btnPrimary}>
              {enviando ? (progressoUpload != null ? `Enviando… ${progressoUpload}%` : 'Enviando…') : emAndamento ? 'Convertendo…' : 'Importar'}
            </button>
            {erro && <span className="text-[12px] text-red-700">{erro}</span>}
          </div>
        </form>

        {st && (
          <div className={`mt-5 bg-white border rounded-lg p-5 text-[13px] ${st.status === 'falhou' ? 'border-red-200' : st.status === 'publicado' ? 'border-green-200' : 'border-blue-200'}`}>
            <ol className="flex gap-2 text-[11px] uppercase tracking-wide mb-3">
              {ETAPAS.map(([id, label], i) => {
                const idxAtual = ETAPAS.findIndex(([e]) => e === st.status)
                const feito = st.status === 'publicado' || (idxAtual > i)
                const atual = st.status === id
                return (
                  <li key={id} className={`px-2 py-0.5 rounded ${atual ? 'bg-blue-600 text-white' : feito ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-400'}`}>
                    {label}
                  </li>
                )
              })}
              {st.status === 'falhou' && <li className="px-2 py-0.5 rounded bg-red-600 text-white">falhou</li>}
            </ol>
            <p className="text-gray-700">
              <strong>{st.fileName}</strong>
              {st.segundos > 0 && <> · {st.segundos} s</>}
              {emAndamento && <span className="text-gray-400"> · atualizado há {Math.min(tick, 99) >= 0 ? 'poucos segundos' : ''}</span>}
            </p>
            {st.note && <p className="text-[12px] text-gray-500 mt-1 font-mono whitespace-pre-wrap">{st.note}</p>}
            {st.error && <p className="text-[12px] text-red-700 mt-2 whitespace-pre-wrap">{st.error}</p>}
            {st.status === 'publicado' && st.editorUrl && (
              <div className="mt-3">
                {st.specs && (
                  <p className="text-[12px] text-gray-600 mb-3">
                    {Object.entries(st.specs).filter(([k]) => !['Fonte', 'Formato'].includes(k)).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                  </p>
                )}
                <div className="flex gap-3 flex-wrap">
                  <a href={st.editorUrl} className={btnPrimary}>Abrir no editor 3D</a>
                  {st.catalogoUrl && <a href={st.catalogoUrl} className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">Ver catálogo público</a>}
                  {st.catalogoUrl && <a href={`${st.catalogoUrl}/editar`} className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">Lista de produtos</a>}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  )
}
