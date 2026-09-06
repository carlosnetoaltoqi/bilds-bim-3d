import { API_URL } from '@/lib/api'
import { BotaoApagar } from '@/components/BotaoApagar'
import { BotaoGerarZip } from '@/components/BotaoGerarZip'

/**
 * / — empresas cadastradas e seus catálogos, com as chamadas para ver, editar e
 * importar. Sem login (A7 de docs/arquitetura-www-servico-de-ingestao.md).
 */

interface Catalogo { id: string; slug: string; title: string; manufacturer: string; layout: string; productCount: number }
interface Empresa { id: string; name: string; customUrl: string; logoUrl: string | null; catalogCount: number }

export const dynamic = 'force-dynamic'

export default async function HomePage() {
  let empresas: Array<Empresa & { catalogos: Catalogo[] }> = []
  let erro: string | null = null
  try {
    const res = await fetch(`${API_URL}/empresas`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`API ${res.status}`)
    const lista = (await res.json()) as Empresa[]
    empresas = await Promise.all(lista.map(async (e) => {
      const r = await fetch(`${API_URL}/empresas/${e.customUrl}/catalogos`, { cache: 'no-store' })
      return { ...e, catalogos: r.ok ? ((await r.json()) as Catalogo[]) : [] }
    }))
  } catch (e: any) {
    erro = `não consegui falar com a API em ${API_URL} — ${e?.message ?? e}`
  }

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-[880px] mx-auto">
        <p className="text-[12px] text-gray-500 mb-1">bilds BIM 3D · POC</p>
        <div className="flex items-baseline justify-between gap-4 flex-wrap mb-6">
          <h1 className="text-2xl font-bold" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Empresas e catálogos</h1>
          <nav aria-label="menu" className="flex gap-2 flex-wrap">
            <a href="/importar?tipo=aq" className="px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold">Importar biblioteca .aq</a>
            <a href="/importar?tipo=cad" className="px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold">Importar peça STEP / IGES / IFC</a>
            <a href="/importar/plugin" className="px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold">Importar plugin do AutoCAD</a>
            <a href="/cad" className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">Converter peça CAD</a>
            <BotaoGerarZip />
            <a href="/empresa/criar" className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">Criar empresa</a>
          </nav>
        </div>

        {erro && <p className="text-[13px] text-red-700 bg-red-50 border border-red-200 rounded p-3">{erro}</p>}
        {!erro && empresas.length === 0 && (
          <p className="text-[13px] text-gray-600">Nenhuma empresa ainda. <a href="/empresa/criar" className="text-[#1e40af] underline">Crie a primeira</a> e depois importe uma biblioteca.</p>
        )}

        {empresas.map((e) => (
          <section key={e.id} className="bg-white border border-gray-200 rounded-lg mb-5">
            <header className="flex items-center gap-3 px-5 py-3 border-b border-gray-100">
              {e.logoUrl ? <img src={`${API_URL}${e.logoUrl}`} alt="" className="w-9 h-9 object-contain rounded border border-gray-200" /> : <span className="w-9 h-9 rounded bg-gray-100" />}
              <div className="flex-1 min-w-0">
                <h2 className="text-[15px] font-bold truncate">{e.name}</h2>
                <p className="text-[11px] text-gray-500">/{e.customUrl} · {e.catalogos.length} catálogo(s)</p>
              </div>
              <a href={`/importar?empresa=${encodeURIComponent(e.customUrl)}`} className="text-[12px] text-[#1e40af] hover:underline">importar para esta empresa →</a>
              <BotaoApagar rota={`/empresas/${encodeURIComponent(e.customUrl)}`} rotulo="apagar empresa"
                confirmacao={`Apagar a empresa "${e.name}" com ${e.catalogos.length} catálogo(s), todos os produtos, importações, geometria e miniaturas? Não tem volta.`} />
            </header>
            {e.catalogos.length === 0 ? (
              <p className="px-5 py-3 text-[12px] text-gray-500">sem catálogos</p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {e.catalogos.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 px-5 py-2.5">
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-semibold truncate">{c.title}</div>
                      <div className="text-[11px] text-gray-500">{c.manufacturer} · {c.productCount} produtos · <code>{c.layout}</code></div>
                    </div>
                    <a href={`/${e.customUrl}/${c.slug}`} className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700">ver</a>
                    <a href={`/${e.customUrl}/${c.slug}/editar`} className="px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold">editar</a>
                    <BotaoApagar rota={`/catalogos/${c.id}`} confirmacao={`Apagar o catálogo "${c.title}" com ${c.productCount} produto(s), geometria, miniaturas e as importações dele? Não tem volta.`} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </main>
  )
}
