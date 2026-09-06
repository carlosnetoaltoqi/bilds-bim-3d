'use client'

/**
 * /importar — sobe uma biblioteca `.aq`/`.zip` ou uma peça CAD `.stp`/`.step`/`.igs`/`.ifc` para o
 * serviço de ingestão (`POST /importacoes`, :4100) e acompanha o status até publicar.
 * Uma página para os dois tipos (E4): o tipo sai da extensão; os campos de peça CAD só
 * aparecem quando o arquivo é CAD. `?tipo=aq` ou `?tipo=cad` (menu da página inicial) restringe
 * o tipo aceito. Sem login (A7). A empresa vem de `?empresa=` (link "importar para esta
 * empresa" na home) ou do seletor.
 *
 * XHR em vez de fetch só para ter progresso real de upload — uma biblioteca chega a 600 MB.
 */

import { FormEvent, Suspense, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { CATALOGO_URL } from '@/servicos/catalogo'
import { CRIADOR_URL } from '@/servicos/criador'
import { BotaoApagar } from '@/components/BotaoApagar'

interface Empresa { id: string; name: string; customUrl: string; catalogCount: number }

interface Importacao {
  importId: string
  tipo: 'aq' | 'cad' | 'plugin'
  status: 'recebido' | 'parseando' | 'gravando' | 'publicado' | 'vazio' | 'falhou' | string
  fileName: string
  note: string | null
  error: string | null
  productCount: number | null
  thumbCount: number | null
  thumbFailed: number | null
  thumbError: string | null
  catalogSlug: string | null
  catalogTitle: string | null
  empresa: string | null
  catalogoUrl: string | null
  editorUrl: string | null
  createdAt: string
  updatedAt: string | null
  segundos: number
  produtoId?: string
  nome?: string
}

const TERMINAL = ['publicado', 'vazio', 'falhou']
const ETAPAS: Array<[string, string]> = [['recebido', 'recebido'], ['parseando', 'lendo'], ['gravando', 'gravando'], ['publicado', 'publicado']]
const EXT_CAD = /\.(stp|step|igs|iges|ifc)$/i
const EXT_OK = /\.(aq|zip|stp|step|igs|iges|ifc)$/i

export default function ImportarPage() {
  // useSearchParams exige Suspense no build estático do Next
  return <Suspense fallback={<main className="min-h-screen bg-gray-50" />}><ImportarPageInner /></Suspense>
}

function ImportarPageInner() {
  const params = useSearchParams()
  const [empresas, setEmpresas] = useState<Empresa[]>([])
  const [empresa, setEmpresa] = useState(params.get('empresa') ?? '')
  const tipo = params.get('tipo') === 'aq' || params.get('tipo') === 'cad' ? (params.get('tipo') as 'aq' | 'cad') : null
  const extOk = tipo === 'aq' ? /\.(aq|zip)$/i : tipo === 'cad' ? EXT_CAD : EXT_OK
  const accept = tipo === 'aq' ? '.aq,.zip,.AQ,.ZIP' : tipo === 'cad' ? '.stp,.step,.igs,.iges,.ifc,.STP,.STEP,.IGS,.IGES,.IFC' : '.aq,.zip,.stp,.step,.igs,.iges,.ifc,.AQ,.ZIP,.STP,.STEP,.IGS,.IGES,.IFC'
  const [file, setFile] = useState<File | null>(null)
  const [fabricante, setFabricante] = useState('')
  const [catalogo, setCatalogo] = useState('')
  const [nome, setNome] = useState('')
  const [deflexao, setDeflexao] = useState('0.2')
  const [enviando, setEnviando] = useState(false)
  const [pct, setPct] = useState<number | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [atual, setAtual] = useState<Importacao | null>(null)
  const [ultimas, setUltimas] = useState<Importacao[]>([])
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const ehCad = !!file && EXT_CAD.test(file.name)
  const emAndamento = !!atual && !TERMINAL.includes(atual.status)

  useEffect(() => {
    fetch(`${CATALOGO_URL}/empresas`).then((r) => (r.ok ? r.json() : [])).then((lista: Empresa[]) => {
      setEmpresas(lista)
      if (!empresa && lista[0]) setEmpresa(lista[0].customUrl)
    }).catch(() => setErro(`não consegui falar com a API em ${CATALOGO_URL}`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function carregarUltimas(emp: string) {
    try {
      const r = await fetch(`${CRIADOR_URL}/importacoes?limite=8${emp ? `&empresa=${encodeURIComponent(emp)}` : ''}`, { cache: 'no-store' })
      if (r.ok) {
        const lista = (await r.json()) as Importacao[]
        setUltimas(lista)
        // recuperação: ao abrir a página, uma importação em andamento volta a ser acompanhada
        const aberta = lista.find((i) => !TERMINAL.includes(i.status))
        if (aberta && !atual) setAtual(aberta)
      }
    } catch { /* serviço fora — a mensagem aparece no envio */ }
  }
  useEffect(() => { void carregarUltimas(empresa) }, [empresa]) // eslint-disable-line react-hooks/exhaustive-deps

  // polling do status
  useEffect(() => {
    if (!atual || !emAndamento) {
      if (timer.current) { clearInterval(timer.current); timer.current = null }
      if (atual && TERMINAL.includes(atual.status)) void carregarUltimas(empresa)
      return
    }
    timer.current = setInterval(async () => {
      try {
        const r = await fetch(`${CRIADOR_URL}/importacoes/${atual.importId}`, { cache: 'no-store' })
        if (r.ok) setAtual((await r.json()) as Importacao)
      } catch { /* serviço fora momentaneamente — tenta de novo */ }
    }, 2000)
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [atual?.importId, emAndamento]) // eslint-disable-line react-hooks/exhaustive-deps

  function enviar(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    if (!extOk.test(file.name)) { setErro(tipo === 'aq' ? 'envie .aq ou .zip' : tipo === 'cad' ? 'envie .stp, .step, .igs ou .ifc' : 'envie .aq, .zip, .stp, .step, .igs ou .ifc'); return }
    setEnviando(true); setErro(null); setAtual(null); setPct(0)
    const fd = new FormData()
    fd.append('file', file)
    if (empresa) fd.append('empresa', empresa)
    if (ehCad) {
      if (fabricante.trim()) fd.append('fabricante', fabricante.trim())
      if (catalogo.trim()) fd.append('catalogo', catalogo.trim())
      fd.append('nome', nome.trim() || file.name.replace(EXT_CAD, ''))
      fd.append('deflexao', deflexao)
    }
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${CRIADOR_URL}/importacoes`)
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) setPct(Math.round((ev.loaded / ev.total) * 100)) }
    xhr.onerror = () => { setErro(`falha de rede ao enviar — o criador de catálogos está de pé em ${CRIADOR_URL}?`); setEnviando(false); setPct(null) }
    xhr.onload = () => {
      setEnviando(false); setPct(null)
      let data: any = {}
      try { data = JSON.parse(xhr.responseText) } catch { /* vazio */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        setErro(data?.message ? (Array.isArray(data.message) ? data.message.join('; ') : String(data.message)) : `serviço respondeu ${xhr.status}`)
        return
      }
      setAtual({ importId: data.importId, tipo: data.tipo, status: data.status ?? 'recebido', fileName: file.name, note: null, error: null,
        productCount: null, thumbCount: null, thumbFailed: null, thumbError: null, catalogSlug: null, catalogTitle: null,
        empresa, catalogoUrl: null, editorUrl: null, createdAt: new Date().toISOString(), updatedAt: null, segundos: 0 })
      setFile(null)
    }
    xhr.send(fd)
  }

  const inputCls = 'w-full border border-gray-300 rounded px-2 py-1.5 text-[13px] bg-white'
  const grande = !!file && file.size > 20 * 1024 * 1024

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-[720px] mx-auto">
        <p className="text-[12px] text-gray-500 mb-1"><a href="/" className="hover:underline">← empresas e catálogos</a></p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>
          {tipo === 'aq' ? 'Importar biblioteca .aq' : tipo === 'cad' ? 'Importar peça STEP / IGES / IFC' : 'Importar biblioteca ou peça'}
        </h1>
        <aside className="mb-6 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] text-gray-600 flex flex-col gap-2">
          {tipo === 'aq' && <>
            <p><strong className="font-semibold text-gray-900">Para que serve:</strong> você tem uma biblioteca exportada do AltoQi Builder (arquivo <code>.aq</code> ou <code>.zip</code>) e quer publicá-la aqui como catálogo navegável com viewer 3D e miniaturas.</p>
            <p><strong className="font-semibold text-gray-900">O que acontece:</strong> o sistema lê todas as peças, propriedades e geometria 3D da biblioteca, cria o catálogo no banco de dados e gera as miniaturas. Bibliotecas grandes podem levar vários minutos — a página acompanha o progresso e pode ser fechada.</p>
            <p><strong className="font-semibold text-gray-900">O que você precisa:</strong> uma empresa já cadastrada (crie uma se ainda não tiver) e o arquivo <code>.aq</code> ou <code>.zip</code> exportado pelo Builder.</p>
          </>}
          {tipo === 'cad' && <>
            <p><strong className="font-semibold text-gray-900">Para que serve:</strong> você tem um arquivo 3D de uma peça individual (STEP, IGES ou IFC) e quer adicioná-la a um catálogo para visualizar no viewer e exportar para o Builder. Cada arquivo vira um produto num catálogo da empresa escolhida.</p>
            <p><strong className="font-semibold text-gray-900">O que acontece:</strong> a geometria é tesselada (STEP/IGES via OpenCASCADE; IFC via interpretador próprio) e o produto é criado no catálogo, pronto para editar no editor 3D ou baixar como <code>.aq</code>.</p>
            <p>Para só inspecionar ou converter o arquivo sem criar produto, use <a href="/cad" className="text-[#1e40af] underline">Converter peça CAD</a>.</p>
          </>}
          {tipo === null && <>
            <p><strong className="font-semibold text-gray-900">Para que serve:</strong> importar uma biblioteca <code>.aq</code>/<code>.zip</code> (catálogo inteiro do Builder) ou uma peça CAD individual (<code>.stp</code>, <code>.igs</code>, <code>.ifc</code>). O tipo é detectado pela extensão: biblioteca cria um catálogo; peça CAD cria um produto num catálogo da empresa.</p>
            <p>Para só converter e inspecionar uma peça sem criar produto, use <a href="/cad" className="text-[#1e40af] underline">Converter peça CAD</a>.</p>
          </>}
        </aside>

        <form onSubmit={enviar} className="bg-white border border-gray-200 rounded-lg p-5 flex flex-col gap-4 text-[13px]">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-gray-600 font-medium">Empresa dona do catálogo</span>
            <select value={empresa} onChange={(e) => setEmpresa(e.target.value)} className={inputCls} disabled={enviando || emAndamento}>
              {empresas.length === 0 && <option value="">(nenhuma empresa — crie uma primeiro)</option>}
              {empresas.map((e) => <option key={e.id} value={e.customUrl}>{e.name} — /{e.customUrl} ({e.catalogCount} catálogo{e.catalogCount === 1 ? '' : 's'})</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-gray-600 font-medium">Arquivo {tipo === 'aq' ? '.aq / .zip' : tipo === 'cad' ? '.stp / .step / .igs / .ifc' : '.aq / .zip / .stp / .step / .igs / .ifc'}</span>
            <input type="file" accept={accept} required disabled={enviando || emAndamento}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[13px]" />
          </label>
          {file && (
            <p className="text-[12px] text-gray-500 -mt-2">
              {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB · {ehCad ? 'peça CAD → um produto' : 'biblioteca → catálogo inteiro'}
              {grande && <span className="text-amber-700"> · arquivo grande: a leitura pode levar minutos — a página acompanha o progresso</span>}
            </p>
          )}
          {ehCad && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Fabricante (série no catálogo)</span><input value={fabricante} onChange={(e) => setFabricante(e.target.value)} className={inputCls} placeholder="STEP ou IFC" /></label>
                <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Catálogo (título)</span><input value={catalogo} onChange={(e) => setCatalogo(e.target.value)} className={inputCls} placeholder="Peças STEP ou Peças IFC" /></label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Nome da peça (vazio = nome do arquivo)</span><input value={nome} onChange={(e) => setNome(e.target.value)} className={inputCls} placeholder={file ? file.name.replace(EXT_CAD, '') : ''} /></label>
                <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Deflexão da malha (mm, STEP/IGES)</span>
                  <select value={deflexao} onChange={(e) => setDeflexao(e.target.value)} className={inputCls} disabled={/\.ifc$/i.test(file!.name)}>
                    <option value="0.5">0,5 — leve</option><option value="0.2">0,2 — padrão</option><option value="0.1">0,1 — fina</option><option value="0.05">0,05 — muito fina</option>
                  </select>
                </label>
              </div>
            </>
          )}
          <div className="flex items-center gap-3">
            <button type="submit" disabled={!file || !empresa || enviando || emAndamento} className="px-4 py-2 rounded bg-[#1e40af] text-white text-[13px] font-semibold disabled:opacity-50">
              {enviando ? (pct != null ? `Enviando… ${pct}%` : 'Enviando…') : emAndamento ? 'Processando…' : 'Importar'}
            </button>
            {erro && <span className="text-[12px] text-red-700">{erro}</span>}
          </div>
          {enviando && pct != null && (
            <div className="h-1.5 bg-gray-200 rounded overflow-hidden"><div className="h-full bg-[#1e40af] transition-all" style={{ width: `${pct}%` }} /></div>
          )}
        </form>

        {atual && <Status imp={atual} onNovo={() => setAtual(null)} />}

        {ultimas.length > 0 && (
          <section className="mt-8">
            <h2 className="text-[12px] uppercase tracking-wide text-gray-500 mb-2">Últimas importações{empresa ? ` — ${empresa}` : ''}</h2>
            <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 text-[13px]">
              {ultimas.map((i) => (
                <li key={i.importId} className="flex items-center gap-3 px-4 py-2">
                  <span className={`text-[11px] px-2 py-0.5 rounded ${i.status === 'publicado' ? 'bg-green-100 text-green-800' : i.status === 'falhou' ? 'bg-red-100 text-red-800' : i.status === 'vazio' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'}`}>{i.status}</span>
                  <span className="text-[11px] text-gray-400 uppercase">{i.tipo}</span>
                  <span className="flex-1 min-w-0 truncate">{i.fileName}{i.catalogTitle ? <span className="text-gray-500"> → {i.catalogTitle}</span> : null}</span>
                  {i.productCount != null && <span className="text-[11px] text-gray-500">{i.productCount} prod.</span>}
                  {!TERMINAL.includes(i.status) && <button onClick={() => setAtual(i)} className="text-[12px] text-[#1e40af] hover:underline">acompanhar</button>}
                  {i.catalogoUrl && <a href={i.catalogoUrl} className="text-[12px] text-[#1e40af] hover:underline">ver</a>}
                  {i.catalogoUrl && <a href={`${i.catalogoUrl}/editar`} className="text-[12px] text-[#1e40af] hover:underline">editar</a>}
                  {TERMINAL.includes(i.status) && (
                    <BotaoApagar rota={`/importacoes/${i.importId}`} base={CRIADOR_URL} onApagado={() => void carregarUltimas(empresa)}
                      confirmacao={`Apagar a importação de "${i.fileName}"${i.productCount ? ` com ${i.productCount} produto(s)` : ''}, geometria e miniaturas? O catálogo fica (recontado).`} />
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  )
}

function Status({ imp, onNovo }: { imp: Importacao; onNovo: () => void }) {
  const idxAtual = ETAPAS.findIndex(([e]) => e === imp.status)
  const terminal = TERMINAL.includes(imp.status)
  const cor = imp.status === 'falhou' ? 'border-red-200' : imp.status === 'publicado' ? 'border-green-200' : imp.status === 'vazio' ? 'border-amber-200' : 'border-blue-200'
  return (
    <div className={`mt-5 bg-white border rounded-lg p-5 text-[13px] ${cor}`}>
      <ol className="flex gap-2 text-[11px] uppercase tracking-wide mb-3 flex-wrap">
        {ETAPAS.map(([id, label], i) => {
          const feito = imp.status === 'publicado' || idxAtual > i
          const atual = imp.status === id
          return <li key={id} className={`px-2 py-0.5 rounded ${atual ? 'bg-blue-600 text-white' : feito ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-400'}`}>{label}</li>
        })}
        {imp.status === 'falhou' && <li className="px-2 py-0.5 rounded bg-red-600 text-white">falhou</li>}
        {imp.status === 'vazio' && <li className="px-2 py-0.5 rounded bg-amber-500 text-white">sem geometria</li>}
      </ol>
      <p className="text-gray-700"><strong>{imp.fileName}</strong>{imp.segundos > 0 && <> · {imp.segundos} s</>}{imp.productCount != null && <> · {imp.productCount} produto(s)</>}
        {imp.thumbCount != null && <> · {imp.thumbCount} miniatura(s){imp.thumbFailed ? <span className="text-amber-700"> ({imp.thumbFailed} falharam)</span> : null}</>}</p>
      {imp.note && <p className="text-[12px] text-gray-500 mt-1 font-mono whitespace-pre-wrap">{imp.note}</p>}
      {imp.error && <p className="text-[12px] text-red-700 mt-2 whitespace-pre-wrap">{imp.error}</p>}
      {imp.thumbError && <p className="text-[12px] text-amber-700 mt-2 whitespace-pre-wrap">miniaturas: {imp.thumbError}</p>}
      {!terminal && <p className="text-[12px] text-blue-700 mt-2">acompanhando… (atualiza a cada 2 s; pode fechar a página — o processamento continua no serviço)</p>}
      {imp.status === 'publicado' && imp.catalogoUrl && (
        <div className="flex gap-3 flex-wrap mt-3">
          <a href={imp.catalogoUrl} className="px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold">Ver catálogo</a>
          <a href={imp.editorUrl ?? `${imp.catalogoUrl}/editar`} className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">{imp.tipo === 'cad' ? 'Abrir a peça no editor 3D' : 'Editar catálogo'}</a>
        </div>
      )}
      {terminal && <button onClick={onNovo} className="mt-4 text-[12px] text-[#1e40af] hover:underline">importar outro arquivo</button>}
    </div>
  )
}
