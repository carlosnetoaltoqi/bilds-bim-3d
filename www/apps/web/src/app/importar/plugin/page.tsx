'use client'

/**
 * /importar/plugin — um plugin de AutoCAD da plataforma Catallog (ex. TupyCAD) vira um catálogo
 * do bilds-bim-3d, editável e exportável para o AltoQi Builder como qualquer outro (S7.17).
 *
 * A DLL do plugin não tem geometria: é uma casca que abre o catálogo web do fabricante. O
 * serviço de ingestão lê nela o host do catálogo (`POST /importacoes/plugin-autocad/inspecionar`),
 * lista as categorias, e a importação (`POST /importacoes/plugin-autocad`) baixa os IGES 3D (e o
 * .rfa Revit) de uma categoria, tessela e publica. Cada download passa pelo formulário do site
 * (nome, e-mail, telefone, empresa, cargo) — os dados são de quem está importando, vão só para o
 * catálogo do fabricante e ficam lembrados neste navegador (localStorage), como o próprio site faz.
 *
 * Depois do 202 a página manda para /importar, que acompanha a importação em andamento.
 */

import { FormEvent, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_URL, INGESTAO_URL } from '@/lib/api'
import { CONVERSORES_URL, inspecionarPlugin } from '@/servicos/conversores'

interface Empresa { id: string; name: string; customUrl: string; catalogCount: number }
interface Categoria { slug: string; name: string; grupos: number; grupos_nomes: string[] }
interface PluginInfo {
  arquivo: string; bytes: number; host: string; hosts: string[]; plugin: string | null; empresa: string | null
  versao: string | null; dotnet: boolean; titulo?: string; categorias?: Categoria[]
}
interface Lead { fullName: string; email: string; mobile: string; company: string; position: string }

const LEAD_KEY = 'bilds-bim-3d.leadDownload'
const LEAD_VAZIO: Lead = { fullName: '', email: '', mobile: '', company: '', position: '' }

function lerErro(xhrOuRes: { status: number; responseText?: string }, corpo?: any): string {
  const msg = corpo?.message
  if (msg) return Array.isArray(msg) ? msg.join('; ') : String(msg)
  return `serviço respondeu ${xhrOuRes.status}`
}

export default function ImportarPluginPage() {
  const router = useRouter()
  const [empresas, setEmpresas] = useState<Empresa[]>([])
  const [empresa, setEmpresa] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [info, setInfo] = useState<PluginInfo | null>(null)
  const [inspecionando, setInspecionando] = useState(false)
  const [host, setHost] = useState('')
  const [categoria, setCategoria] = useState('')
  const [igsPorGrupo, setIgsPorGrupo] = useState('1')
  const [deflexao, setDeflexao] = useState('0.2')
  const [lead, setLead] = useState<Lead>(LEAD_VAZIO)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_URL}/empresas`).then((r) => (r.ok ? r.json() : [])).then((lista: Empresa[]) => {
      setEmpresas(lista)
      if (lista[0]) setEmpresa(lista[0].customUrl)
    }).catch(() => setErro(`não consegui falar com a API em ${API_URL}`))
    try {
      const salvo = localStorage.getItem(LEAD_KEY)
      if (salvo) setLead({ ...LEAD_VAZIO, ...JSON.parse(salvo) })
    } catch { /* sem localStorage */ }
  }, [])

  async function inspecionar() {
    if (!file) return
    setInspecionando(true); setErro(null); setInfo(null)
    try {
      const r = await inspecionarPlugin(file)
      let corpo: any = null
      try { corpo = await r.json() } catch { /* vazio */ }
      if (!r.ok) { setErro(lerErro(r, corpo)); return }
      const i = corpo as PluginInfo
      setInfo(i)
      setHost(i.host)
      const cats = i.categorias ?? []
      setCategoria(cats[0]?.slug ?? '')
    } catch {
      setErro(`falha de rede — o serviço de conversores está de pé em ${CONVERSORES_URL}?`)
    } finally {
      setInspecionando(false)
    }
  }

  function enviar(e: FormEvent) {
    e.preventDefault()
    if (!file || !info || !categoria) return
    setEnviando(true); setErro(null)
    const fd = new FormData()
    fd.append('file', file)
    if (empresa) fd.append('empresa', empresa)
    if (host.trim() && host.trim() !== info.host) fd.append('host', host.trim())
    fd.append('categoria', categoria)
    fd.append('igsPorGrupo', igsPorGrupo)
    fd.append('deflexao', deflexao)
    for (const k of Object.keys(lead) as Array<keyof Lead>) fd.append(k, lead[k].trim())
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${INGESTAO_URL}/importacoes/plugin-autocad`)
    xhr.onerror = () => { setErro(`falha de rede ao enviar — o serviço de ingestão está de pé em ${INGESTAO_URL}?`); setEnviando(false) }
    xhr.onload = () => {
      let corpo: any = {}
      try { corpo = JSON.parse(xhr.responseText) } catch { /* vazio */ }
      if (xhr.status < 200 || xhr.status >= 300) { setErro(lerErro(xhr, corpo)); setEnviando(false); return }
      try { localStorage.setItem(LEAD_KEY, JSON.stringify(lead)) } catch { /* sem localStorage */ }
      router.push(`/importar?empresa=${encodeURIComponent(empresa)}`)
    }
    xhr.send(fd)
  }

  const inputCls = 'w-full border border-gray-300 rounded px-2 py-1.5 text-[13px] bg-white'
  const cats = info?.categorias ?? []
  const catAtual = cats.find((c) => c.slug === categoria)
  const leadOk = Object.values(lead).every((v) => v.trim()) && lead.email.includes('@')

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-[720px] mx-auto">
        <p className="text-[12px] text-gray-500 mb-1"><a href="/" className="hover:underline">← empresas e catálogos</a></p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Importar plugin do AutoCAD</h1>
        <p className="text-[13px] text-gray-600 mb-6">
          Plugins de fabricante feitos na plataforma <strong>Catallog</strong> (ex. <code>TupyCAD.dll</code>, em
          <code> C:\Program Files\Autodesk\ApplicationPlugins\&lt;nome&gt;.bundle\</code>) não trazem geometria: abrem o catálogo web
          do fabricante. Aqui a DLL diz qual catálogo é; você escolhe a categoria; o serviço baixa os arquivos 3D (IGES) e as
          famílias Revit, tessela e publica um catálogo — que depois se edita e se exporta para o AltoQi Builder como <code>.aq</code>.
        </p>

        <form onSubmit={enviar} className="bg-white border border-gray-200 rounded-lg p-5 flex flex-col gap-4 text-[13px]">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-gray-600 font-medium">1 · DLL do plugin</span>
            <div className="flex gap-2 items-center flex-wrap">
              <input type="file" accept=".dll,.DLL" required disabled={enviando}
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setInfo(null) }} className="text-[13px]" />
              <button type="button" onClick={inspecionar} disabled={!file || inspecionando || enviando}
                className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700 disabled:opacity-50">
                {inspecionando ? 'Lendo a DLL e o catálogo…' : 'Inspecionar'}
              </button>
            </div>
          </label>

          {info && (
            <div className="rounded border border-blue-100 bg-blue-50 p-3 text-[12px] text-gray-700 flex flex-col gap-1">
              <div><strong>{info.plugin ?? info.arquivo}</strong>{info.versao ? ` ${info.versao}` : ''}{info.empresa ? ` · ${info.empresa}` : ''} · {(info.bytes / 1024).toFixed(0)} KB{info.dotnet ? ' · .NET' : ''}</div>
              <div>catálogo web: <strong>{info.titulo ?? '?'}</strong> em <code>{info.host}</code></div>
              <div>{cats.length} categoria(s): {cats.map((c) => `${c.name} (${c.grupos} grupos)`).join(' · ')}</div>
            </div>
          )}

          {info && (
            <>
              <label className="flex flex-col gap-1">
                <span className="text-[12px] text-gray-600 font-medium">Empresa dona do catálogo</span>
                <select value={empresa} onChange={(e) => setEmpresa(e.target.value)} className={inputCls} disabled={enviando}>
                  {empresas.length === 0 && <option value="">(nenhuma empresa — crie uma primeiro)</option>}
                  {empresas.map((e) => <option key={e.id} value={e.customUrl}>{e.name} — /{e.customUrl} ({e.catalogCount} catálogo{e.catalogCount === 1 ? '' : 's'})</option>)}
                </select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-[12px] text-gray-600 font-medium">2 · Categoria a importar</span>
                  <select value={categoria} onChange={(e) => setCategoria(e.target.value)} className={inputCls} disabled={enviando}>
                    {cats.map((c) => <option key={c.slug} value={c.slug}>{c.name} — {c.grupos} grupo{c.grupos === 1 ? '' : 's'}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[12px] text-gray-600 font-medium">Host do catálogo (o da DLL, ou outro do mesmo fabricante)</span>
                  <input value={host} onChange={(e) => setHost(e.target.value)} className={inputCls} placeholder={info.host} disabled={enviando} />
                </label>
              </div>
              {catAtual && (
                <p className="text-[12px] text-gray-500 -mt-2">grupos: {catAtual.grupos_nomes.join(', ')}</p>
              )}
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-[12px] text-gray-600">Peças 3D por grupo (família)</span>
                  <select value={igsPorGrupo} onChange={(e) => setIgsPorGrupo(e.target.value)} className={inputCls} disabled={enviando}>
                    <option value="1">1 — um tamanho por família (estudo)</option>
                    <option value="3">3 — três tamanhos por família</option>
                    <option value="-1">todos — cada tamanho vira uma peça (pode ser centenas de MB)</option>
                    <option value="0">nenhum — só as famílias Revit (sem 3D, sem peças)</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[12px] text-gray-600">Deflexão da malha (mm)</span>
                  <select value={deflexao} onChange={(e) => setDeflexao(e.target.value)} className={inputCls} disabled={enviando}>
                    <option value="0.5">0,5 — leve</option><option value="0.2">0,2 — padrão</option><option value="0.1">0,1 — fina</option>
                  </select>
                </label>
              </div>

              <fieldset className="border border-gray-200 rounded p-3 flex flex-col gap-2">
                <legend className="text-[12px] text-gray-600 font-medium px-1">3 · Formulário de download do catálogo do fabricante</legend>
                <p className="text-[12px] text-gray-500">
                  O site do fabricante pede estes dados a cada arquivo baixado. Use os <strong>seus</strong> dados: eles vão só para o
                  catálogo dele (não são gravados aqui) e o download vale os Termos de Uso do site.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  {([['fullName', 'Nome'], ['email', 'E-mail'], ['mobile', 'Telefone'], ['company', 'Empresa'], ['position', 'Cargo']] as Array<[keyof Lead, string]>).map(([k, rot]) => (
                    <label key={k} className="flex flex-col gap-1">
                      <span className="text-[12px] text-gray-600">{rot}</span>
                      <input value={lead[k]} onChange={(e) => setLead({ ...lead, [k]: e.target.value })} className={inputCls} required
                        type={k === 'email' ? 'email' : 'text'} disabled={enviando} />
                    </label>
                  ))}
                </div>
              </fieldset>
            </>
          )}

          <div className="flex items-center gap-3">
            <button type="submit" disabled={!file || !info || !categoria || !empresa || !leadOk || enviando}
              className="px-4 py-2 rounded bg-[#1e40af] text-white text-[13px] font-semibold disabled:opacity-50">
              {enviando ? 'Enviando…' : 'Importar categoria'}
            </button>
            {erro && <span className="text-[12px] text-red-700">{erro}</span>}
            {!info && file && !erro && <span className="text-[12px] text-gray-500">inspecione a DLL para escolher a categoria</span>}
          </div>
        </form>
      </div>
    </main>
  )
}
