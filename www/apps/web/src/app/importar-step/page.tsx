'use client'

/**
 * /importar-step — sobe um .stp/.step, a API tessela com OpenCASCADE e cria um
 * produto num catálogo; daí o editor 3D abre a peça como qualquer outra.
 * Sem login (rota fora do matcher do middleware), como o resto da POC de edição.
 */

import { FormEvent, useState } from 'react'
import { API_URL } from '@/lib/api'
import { Field, btnPrimary, inputCls } from '@/components/bim-editor/InfoForm'

interface Resultado {
  produtoId: string
  empresa: string
  catalogSlug: string
  editorUrl: string
  catalogoUrl: string
  triangulos: number
  partes: number
  bbox_mm: number[]
  unidade: string
}

export default function ImportarStepPage() {
  const [file, setFile] = useState<File | null>(null)
  const [fabricante, setFabricante] = useState('STEP')
  const [catalogo, setCatalogo] = useState('Peças STEP')
  const [nome, setNome] = useState('')
  const [deflexao, setDeflexao] = useState('0.2')
  const [empresa, setEmpresa] = useState('')
  const [busy, setBusy] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [res, setRes] = useState<Resultado | null>(null)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setErro(null)
    setRes(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('fabricante', fabricante)
      fd.append('catalogo', catalogo)
      fd.append('nome', nome || file.name.replace(/\.(stp|step)$/i, ''))
      fd.append('deflexao', deflexao)
      if (empresa.trim()) fd.append('empresa', empresa.trim())
      const r = await fetch(`${API_URL}/step/importar`, { method: 'POST', body: fd })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data?.message ? String(data.message) : `API ${r.status}`)
      setRes(data as Resultado)
    } catch (err: any) {
      setErro(err.message ?? String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 flex items-start justify-center py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="w-full max-w-[560px]">
        <p className="text-[12px] text-gray-500 mb-1">bilds BIM 3D · POC de edição</p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Importar peça STEP</h1>
        <p className="text-[13px] text-gray-600 mb-6">
          O arquivo é tesselado no servidor com OpenCASCADE (metros, Y-up, cor por face) e entra num catálogo como produto.
          Depois é só editar, e exportar em IFC4 ou <code>.aq</code>.
        </p>

        <form onSubmit={enviar} className="bg-white border border-gray-200 rounded-lg p-5 flex flex-col gap-4 text-[13px]">
          <Field label="Arquivo .stp / .step">
            <input type="file" accept=".stp,.step,.STP,.STEP" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[13px]" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Fabricante (série no catálogo)"><input value={fabricante} onChange={(e) => setFabricante(e.target.value)} className={inputCls} /></Field>
            <Field label="Catálogo (título)"><input value={catalogo} onChange={(e) => setCatalogo(e.target.value)} className={inputCls} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nome da peça (vazio = nome do arquivo)"><input value={nome} onChange={(e) => setNome(e.target.value)} className={inputCls} placeholder={file ? file.name.replace(/\.(stp|step)$/i, '') : ''} /></Field>
            <Field label="Deflexão da malha (mm)">
              <select value={deflexao} onChange={(e) => setDeflexao(e.target.value)} className={inputCls}>
                <option value="0.5">0,5 — leve</option>
                <option value="0.2">0,2 — padrão</option>
                <option value="0.1">0,1 — fina</option>
                <option value="0.05">0,05 — muito fina</option>
              </select>
            </Field>
          </div>
          <Field label="Empresa (customUrl; vazio = a primeira cadastrada)"><input value={empresa} onChange={(e) => setEmpresa(e.target.value)} className={inputCls} placeholder="poc-edicao" /></Field>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={!file || busy} className={btnPrimary}>{busy ? 'Tesselando…' : 'Importar e abrir no editor'}</button>
            {erro && <span className="text-[12px] text-red-700">{erro}</span>}
          </div>
        </form>

        {res && (
          <div className="mt-5 bg-white border border-green-200 rounded-lg p-5 text-[13px]">
            <p className="font-semibold text-green-800 mb-2">Importado.</p>
            <p className="text-gray-700 mb-3">
              {res.partes} sólido(s) · {res.triangulos.toLocaleString('pt-BR')} triângulos · {res.bbox_mm.map((v) => v.toFixed(1)).join(' × ')} mm · unidade do arquivo {res.unidade}
            </p>
            <div className="flex gap-3 flex-wrap">
              <a href={res.editorUrl} className={btnPrimary}>Abrir no editor 3D</a>
              <a href={res.catalogoUrl} className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">Ver catálogo público</a>
              <a href={`${res.catalogoUrl}/editar`} className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">Lista de produtos</a>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
