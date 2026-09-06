'use client'

/**
 * /importar/revit — famílias Revit (`.rfa` solto ou `.zip` com as famílias, os type catalogs `.txt` e,
 * quando houver, a geometria irmã `.ifc`/`.stp`/`.igs` de mesmo nome) viram um catálogo do bilds-bim-3d,
 * editável e exportável para o AltoQi Builder como qualquer outro.
 *
 * A geometria de um `.rfa` é proprietária e não é legível fora do Revit (`docs/conhecimento/revit-familias.md`).
 * O que se lê são os tipos com todos os parâmetros, a categoria e a miniatura. A geometria vem do arquivo
 * irmão quando existe; senão, cada tipo recebe uma forma representativa gerada a partir das cotas do tipo
 * (perfil I/U, tubo, caixa, chapa perfilada), com a ressalva gravada na série e na spec "Geometria 3D".
 *
 * Envia para `POST /importacoes/familias-revit` (:4100) e, depois do 202, manda para /importar, que
 * acompanha a importação em andamento (a inspeção síncrona recusa na hora o que não tem família).
 */

import { FormEvent, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { CATALOGO_URL } from '@/servicos/catalogo'
import { CRIADOR_URL } from '@/servicos/criador'

interface Empresa { id: string; name: string; customUrl: string; catalogCount: number }

const EXT_OK = /\.(rfa|rvt|zip)$/i

export default function ImportarRevitPage() {
  const router = useRouter()
  const [empresas, setEmpresas] = useState<Empresa[]>([])
  const [empresa, setEmpresa] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [apsDisponivel, setApsDisponivel] = useState<boolean | null>(null)
  const [usarAps, setUsarAps] = useState(false)
  const [catalogo, setCatalogo] = useState('')
  const [fabricante, setFabricante] = useState('')
  const [comprimento, setComprimento] = useState('1000')
  const [deflexao, setDeflexao] = useState('0.2')
  const [enviando, setEnviando] = useState(false)
  const [pct, setPct] = useState<number | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${CATALOGO_URL}/empresas`).then((r) => (r.ok ? r.json() : [])).then((lista: Empresa[]) => {
      setEmpresas(lista)
      if (lista[0]) setEmpresa(lista[0].customUrl)
    }).catch(() => setErro(`não consegui falar com a API em ${CATALOGO_URL}`))
    fetch(`${CRIADOR_URL}/importacoes/familias-revit/aps`).then((r) => (r.ok ? r.json() : { disponivel: false }))
      .then((d: { disponivel: boolean }) => setApsDisponivel(!!d.disponivel)).catch(() => setApsDisponivel(false))
  }, [])

  function enviar(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    if (!EXT_OK.test(file.name)) { setErro('envie um .rfa, um projeto .rvt ou um .zip com as famílias'); return }
    setEnviando(true); setErro(null); setPct(0)
    const fd = new FormData()
    fd.append('file', file)
    if (empresa) fd.append('empresa', empresa)
    fd.append('usarAps', usarAps && apsDisponivel ? 'true' : 'false')
    if (catalogo.trim()) fd.append('catalogo', catalogo.trim())
    if (fabricante.trim()) fd.append('fabricante', fabricante.trim())
    if (comprimento.trim()) fd.append('comprimentoMm', comprimento.trim())
    fd.append('deflexao', deflexao)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${CRIADOR_URL}/importacoes/familias-revit`)
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
      router.push(`/importar?empresa=${encodeURIComponent(empresa)}`)
    }
    xhr.send(fd)
  }

  const inputCls = 'w-full border border-gray-300 rounded px-2 py-1.5 text-[13px] bg-white'
  const ehZip = !!file && /\.zip$/i.test(file.name)
  const ehRvt = !!file && /\.rvt$/i.test(file.name)

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-[720px] mx-auto">
        <p className="text-[12px] text-gray-500 mb-1"><a href="/" className="hover:underline">← empresas e catálogos</a></p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Importar famílias Revit</h1>
        <aside className="mb-6 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] text-gray-600 flex flex-col gap-2">
          <p><strong className="font-semibold text-gray-900">Para que serve:</strong> você tem famílias Revit de um fabricante (<code>.rfa</code>, geralmente num <code>.zip</code> com os type catalogs <code>.txt</code>) e quer publicá-las aqui como catálogo com viewer 3D — e depois exportar para o AltoQi Builder como <code>.aq</code>. Cada tipo da família vira um produto; a família vira a série.</p>
          <p><strong className="font-semibold text-gray-900">O que acontece:</strong> o sistema lê de cada <code>.rfa</code> a categoria, a versão do Revit e a tabela de tipos com todos os parâmetros (fabricante, modelo, dimensões, material), e do <code>.txt</code> ao lado os tipos que o Revit carrega. <strong>A geometria 3D de um <code>.rfa</code> é proprietária e não é legível fora do Revit.</strong> Se houver um arquivo <code>.ifc</code>, <code>.stp</code> ou <code>.igs</code> com o mesmo nome da família (exportado do Revit ou baixado do portal do fabricante), a geometria real vem dele. Senão, cada tipo recebe uma <em>forma representativa</em> montada a partir das suas cotas (perfil I/U, tubo retangular ou redondo, caixa, chapa perfilada), marcada como aproximada na série e na ficha do produto.</p>
          <p><strong className="font-semibold text-gray-900">Projeto <code>.rvt</code>:</strong> as famílias embutidas num projeto não são extraíveis fora do Revit. Um projeto entra pelo IFC dele: ou você coloca o <code>.ifc</code> exportado ao lado (mesmo nome), ou marca abaixo <em>usar a Autodesk Platform Services</em> e o projeto é traduzido em IFC na nuvem da Autodesk (o arquivo sai desta máquina; cada projeto consome tokens da conta APS configurada no serviço; o mesmo projeto não é traduzido duas vezes). Cada tipo de família colocado no projeto vira um produto com a geometria real.</p>
        </aside>

        <form onSubmit={enviar} className="bg-white border border-gray-200 rounded-lg p-5 flex flex-col gap-4 text-[13px]">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-gray-600 font-medium">Empresa dona do catálogo</span>
            <select value={empresa} onChange={(e) => setEmpresa(e.target.value)} className={inputCls} disabled={enviando}>
              {empresas.length === 0 && <option value="">(nenhuma empresa — crie uma primeiro)</option>}
              {empresas.map((e) => <option key={e.id} value={e.customUrl}>{e.name} — /{e.customUrl} ({e.catalogCount} catálogo{e.catalogCount === 1 ? '' : 's'})</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-gray-600 font-medium">Arquivo .rfa, projeto .rvt ou .zip com famílias/projetos</span>
            <input type="file" accept=".rfa,.rvt,.zip,.RFA,.RVT,.ZIP" required disabled={enviando}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[13px]" />
          </label>
          {file && (
            <p className="text-[12px] text-gray-500 -mt-2">
              {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB · {ehZip ? 'pacote de famílias/projetos → catálogo inteiro' : ehRvt ? 'projeto → um produto por tipo de família colocado' : 'uma família → uma série com seus tipos'}
            </p>
          )}
          <fieldset className={`rounded border px-3 py-2 flex flex-col gap-1 ${apsDisponivel ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-gray-50'}`}>
            <legend className="text-[12px] text-gray-600 font-medium px-1">Projetos .rvt no envio</legend>
            <label className="flex items-start gap-2 text-[13px]">
              <input type="checkbox" checked={usarAps && !!apsDisponivel} disabled={!apsDisponivel || enviando} onChange={(e) => setUsarAps(e.target.checked)} className="mt-0.5" />
              <span>
                Usar a <strong>Autodesk Platform Services</strong> para traduzir projetos <code>.rvt</code> em IFC
                {apsDisponivel === false && <span className="text-gray-500"> — indisponível: o serviço não tem APS_CLIENT_ID/APS_CLIENT_SECRET (veja <code>.env.example</code>)</span>}
                {apsDisponivel && <span className="text-amber-800"> — cobrado por projeto na conta APS; o arquivo sai para a nuvem da Autodesk</span>}
                {apsDisponivel === null && <span className="text-gray-400"> — consultando o serviço…</span>}
              </span>
            </label>
            <p className="text-[12px] text-gray-500">Sem marcar, um projeto só entra se houver um <code>.ifc</code> de mesmo nome ao lado; famílias <code>.rfa</code> não passam pela APS (o Model Derivative não as aceita).</p>
          </fieldset>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Catálogo (título; vazio = nome do arquivo)</span><input value={catalogo} onChange={(e) => setCatalogo(e.target.value)} className={inputCls} placeholder={file ? file.name.replace(EXT_OK, '') : ''} /></label>
            <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Fabricante (vazio = o parâmetro Manufacturer das famílias)</span><input value={fabricante} onChange={(e) => setFabricante(e.target.value)} className={inputCls} /></label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Trecho das formas representativas (mm)</span>
              <select value={comprimento} onChange={(e) => setComprimento(e.target.value)} className={inputCls}>
                <option value="500">500</option><option value="1000">1000 — padrão</option><option value="2000">2000</option><option value="3000">3000</option><option value="6000">6000</option>
              </select>
            </label>
            <label className="flex flex-col gap-1"><span className="text-[12px] text-gray-600">Deflexão da malha (mm, geometria irmã STEP/IGES)</span>
              <select value={deflexao} onChange={(e) => setDeflexao(e.target.value)} className={inputCls}>
                <option value="0.5">0,5 — leve</option><option value="0.2">0,2 — padrão</option><option value="0.1">0,1 — fina</option>
              </select>
            </label>
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={!file || !empresa || enviando} className="px-4 py-2 rounded bg-[#1e40af] text-white text-[13px] font-semibold disabled:opacity-50">
              {enviando ? (pct != null && pct < 100 ? `Enviando… ${pct}%` : 'Lendo as famílias…') : 'Importar'}
            </button>
            {erro && <span className="text-[12px] text-red-700">{erro}</span>}
          </div>
          {enviando && pct != null && (
            <div className="h-1.5 bg-gray-200 rounded overflow-hidden"><div className="h-full bg-[#1e40af] transition-all" style={{ width: `${pct}%` }} /></div>
          )}
        </form>
        <p className="mt-4 text-[12px] text-gray-500">Depois do envio a página de <a href="/importar" className="text-[#1e40af] underline">importações</a> acompanha o progresso; o catálogo publicado pode ser editado e exportado como <code>.aq</code>.</p>
      </div>
    </main>
  )
}
